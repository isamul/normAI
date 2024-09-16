import chainlit as cl
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from uuid import uuid4

load_dotenv()

from langfuse.callback import CallbackHandler
langfuse_handler = CallbackHandler(
    public_key="pk-lf-a94df179-5c70-4c79-8ddb-719b8c31e30b",
    secret_key="sk-lf-23574838-ebc7-40ae-a3fd-82e443e0cdc3",
    host="https://cloud.langfuse.com"
)

#class AgentState(TypedDict):
#    messages: Annotated[list, add_messages]


#model = ChatOpenAI(model="gpt-4o-mini", streaming=True)

#async def call_model(state: AgentState):
#    messages = state["messages"]
#    response = await model.ainvoke(messages)
    # We return a list, because this will get added to the existing list
#    return {"messages": response}


#workflow = StateGraph(AgentState)

#workflow.add_node('agent', call_model)
#workflow.set_entry_point('agent')
#workflow.add_edge('agent', END)

#memory = MemorySaver()
#app = workflow.compile(checkpointer=memory)

from base_agent.agent import graph


@cl.on_chat_start
def on_chat_start():
    cl.user_session.set("chat_id", str(uuid4()))





@cl.on_message
async def run_convo(message: cl.Message):

    msg = cl.Message(content="")
    inputs = [HumanMessage(content=message.content)]

    config = {
    "configurable": {"thread_id": cl.user_session.get("chat_id")},
    #"callbacks": [cl.LangchainCallbackHandler(
    #    to_ignore=["ChannelRead", "RunnableLambda", "ChannelWrite", "__start__", "_execute", "agent", "action", "should_continue", "ChatOpenAI", "_write", "TaskRouter"]
    #)
    #langfuse_handler
    #]
}

    #async for event in graph.astream_events({"messages": inputs}, config=config, version="v1"):
    #    print(event)
    #    kind = event["event"]
    #    if kind == "on_chat_model_stream":
    #        content = event["data"]["chunk"].content
    #        if content:

    #            await msg.stream_token(content)
                
    #await msg.update()
    expert_events = ["InvokeExpertModel", "InitialRetrieval", "CreatePlan", "DataBaseHandler", "UserHandler", "HumanFeedback", "FeedbackHandler", "CalculationHandler", "LLMHandler", "OutputHandler"]
    documentSearchStep_cache = None
    expertModelStep_cache = None
    contextRetrievalStep_cache = None
    createPlanStep_cache = None
    databaseHandlerStep_cache = None
    userHandlerStep_cache = None
    humanFeedback = False
    #documentSearchInput = {}
    user_input = ""
    #async with cl.Step(name="LangGraph") as step:
    async for event in graph.astream_events({"messages": inputs}, config=config, version="v2"):
        
        if event["event"] == "on_chat_model_stream" and event['metadata'].get('langgraph_node','') == "agent":
            #print(event["data"]["chunk"].content, end="", flush=True)
            content = event["data"]["chunk"].content
            if content:
                await msg.send()
                await msg.stream_token(content)
        if event['metadata'].get('langgraph_node','') == "DocumentSearch":
            if event["event"] == "on_tool_start" or event["event"] == "on_tool_end":
                if event["event"] == "on_tool_start":
                    async with cl.Step(name="DocumentSearch") as documentSearchStep:
                        documentSearchStep_cache = documentSearchStep

                        documentSearchInput = {'input': event["data"]["input"]["query"], 'data_type': event["data"]["input"]["data_type"]}
                        documentSearchStep.input = documentSearchInput

                        await documentSearchStep.update()
                    
                elif event["event"] == "on_tool_end":
                    #async with cl.Step(name="DocumentSearch") as documentSearchStep:
                    async with documentSearchStep_cache as documentSearchStep:
                        output_dict = {'output': event["data"]["output"].content}
                        #output = output_dict
                        #documentSearchStep.input = documentSearchInput
                        documentSearchStep.output = output_dict
                    
                        await documentSearchStep.update()
                  
                print("Event type: " + str(event["event"]) + " Event data: " + str(event["data"]))
        
        if event['metadata'].get('langgraph_node','') == "GetHelp" and event["event"] == "on_chain_stream":
            content = event["data"]

            #print("Event type: " + event['event'] + " Help content: " + str(content))
            await msg.send()
            await msg.stream_token(content['chunk']['messages'][0].content)
        
        if event['metadata'].get('langgraph_node','') in expert_events:
            if event['metadata'].get('langgraph_node','') == "InvokeExpertModel" and expertModelStep_cache is None:
                
                async with cl.Step(name="Expert") as expertModelStep:
                    expertModelStep_cache = expertModelStep
                    # add expert task to step input

                    input = event['data']
                    task = event["data"]["input"]["messages"][-1].tool_calls[0]["args"]['task']
                    expertModelStep.input = {'task': task}

                #await expertModelStep.update()

            else:
                async with expertModelStep_cache as expertModelStep:
                # nest all subnodes here
                    if event['metadata'].get('langgraph_node','') == "InitialRetrieval" and event["event"] == "on_chat_model_end":
                        # extract database call for initial retrieval
                        
                        async with cl.Step(name="ContextRetrieval") as contextRetrievalStep:
                            contextRetrievalStep_cache = contextRetrievalStep
                            input = {'search_query': event["data"]["output"].tool_calls[0]['args']['query']}
                            contextRetrievalStep.input = input
                            await contextRetrievalStep.update()
                        
                    elif event['metadata'].get('langgraph_node','') == "InitialRetrieval" and event["event"] == "on_chain_start" and event["name"] == "_write":
                        async with contextRetrievalStep_cache as contextRetrievalStep:
                            output = {'context': event["data"]["input"]["context"]}
                            contextRetrievalStep.output = output
                            await contextRetrievalStep.update()

                    #print("Event type: " + event['event'])


                    if event['metadata'].get('langgraph_node','') == "CreatePlan" and createPlanStep_cache is None and event["event"] == "on_chat_model_start":
                        async with cl.Step(name="CreatePlan") as createPlanStep:
                            createPlanStep_cache = createPlanStep
                    
                    elif event['metadata'].get('langgraph_node','') == "CreatePlan" and createPlanStep_cache is not None and event["event"] == "on_chat_model_stream":
                        async with createPlanStep_cache as createPlanStep:
                            chunk = event['data']["chunk"].content
                            
                            await createPlanStep.stream_token(chunk)

                    if event['metadata'].get('langgraph_node','') == "DataBaseHandler" and databaseHandlerStep_cache is None and event["event"] == "on_chain_end":
                        async with cl.Step(name="DataBaseCall") as databaseHandlerStep:
                            databaseHandlerStep_cache = databaseHandlerStep
                            
                            res = event['data']["output"]['step_results'][0]
                            output = {'Step number': res.step_number, 'Result': res.result}
                            databaseHandlerStep.output = output
                            await databaseHandlerStep.update()

                    if event['metadata'].get('langgraph_node','') == "UserHandler" and event["event"] == "on_chain_end" and userHandlerStep_cache is None:
                        user_question = event['data']["output"]['messages'][0].content
                        with cl.Step(name="UserHandler") as userHandlerStep:
                            userHandlerStep_cache = userHandlerStep
                            userHandlerStep.input = ""

                        print("User question: " + user_question)
                        res = await cl.AskUserMessage(content=user_question).send()
                        
                        if res:
                            user_input = res.content
                            userHandlerStep.input = res
                            await userHandlerStep.update()

                            # implement logic for graph invocation

                    if event['metadata'].get('langgraph_node','') == "HumanFeedback" and event["event"] == "on_chain_end":
                        if humanFeedback == False:
                            humanFeedback = True
                        else:
                            # implement logic for graph invocation
                            user_feedback = [HumanMessage(content=user_input)]
                            graph.update_state(config, {"messages": user_feedback}, as_node="HumanFeedback")
                        
                    
                    # implement LLMHandler and CalculationHandler


                    

                await expertModelStep.update()
            
                #if humanFeedback == False:
                    
                    
            

                #async with cl.Step(name="CreatePlan") as createPlanStep:
                #    createPlanStep_cache = createPlanStep
                #    input = event['data']
                #    createPlanStep.input = input
                #    await createPlanStep.update()



            #content = event["data"]
            #print("Event type: " + event['event'] + " Expert content: " + str(content))
            #await msg.send()
            #await msg.stream_token(content['input']['query'])
    if humanFeedback:
        async for event in graph.astream_events(None, config=config, version="v2"):
            pass
            # possible nodes: DataBaseHandler, UserHandler, LLMHandler, CalculationHandler, OutputHandler




    await msg.update()

if __name__ == "__main__":
    from chainlit.cli import run_chainlit
    run_chainlit(__file__)