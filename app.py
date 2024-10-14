"""
This Python file is a Chainlit application that integrates with various services and handles chat interactions.

Imports and Setup:
- Imports necessary modules like asyncio, chainlit, dotenv, and others.
- Loads environment variables using load_dotenv.

Starter Messages:
- Defines an asynchronous function `set_starters` that returns a list of starter messages with labels, messages, and icons.

Chat Session Initialization:
- Defines `on_chat_start` to initialize a chat session with a unique ID and a `conclusion` variable.
- Starts monitoring the `conclusion` session variable.

Message Handling:
- Defines `add_message` to send and update messages.
- Additional functions (not shown in this excerpt) handle sending conclusions, monitoring session variables, and handling changes.

Chat Interaction:
- Additional functions (not shown in this excerpt) handle incoming messages and process them through a series of steps and events.

Main Execution:
- Runs the Chainlit application if the script is executed directly.
"""

import asyncio
import chainlit as cl
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from uuid import uuid4


load_dotenv()


from base_agent.agent import graph

@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="Was kann die App?",
            message="Was kann diese App?",
            icon="/public/bulb.svg",
            ),

        cl.Starter(
            label="Berechne die Schneelast für ein Flachdach",
            message="Berechne die Schneelast für ein Flachdach",
            icon="/public/function.svg",
            ),
        cl.Starter(
            label="Übersicht über Dachformen",
            message="Was gibt es für Dachformen?",
            icon="/public/pencil.svg",
            ),
        cl.Starter(
            label="Was ist ein Formbeiwert?",
            message="Was ist ein Formbeiwert?",
            icon="/public/mg.svg",
            )
        ]

@cl.on_chat_start
def on_chat_start():
    cl.user_session.set("chat_id", str(uuid4()))
    cl.user_session.set("conclusion", None)
    asyncio.create_task(monitor_session_variable("conclusion"))

async def add_message(msg: cl.Message):
    await msg.send()
    await msg.update()

async def send_conclusion():

    elements = []
    ref_str = ""
    for reference in cl.user_session.get("conclusion")['references']:
        elements.append(cl.Text(name="References", content=reference, display='inline'))

    concl_msg = cl.Message(content=cl.user_session.get("conclusion")['conclusion'], elements=elements)
    #ref_msg = cl.Message(content="References: \n" + ref_str)
    await add_message(concl_msg)
    #await add_message(ref_msg)
    cl.user_session.set("conclusion", None)

async def monitor_session_variable(variable_name, check_interval=1):
    previous_value = cl.user_session.get(variable_name)
    while True:
        await asyncio.sleep(check_interval)
        current_value = cl.user_session.get(variable_name)
        if current_value != previous_value:
            await handle_session_variable_change(variable_name, current_value)
            previous_value = current_value

async def handle_session_variable_change(variable_name, new_value):
    if variable_name == "conclusion" and new_value:
        await send_conclusion()


# main function handling the interaction between chainlit and NormGraph
@cl.on_message
async def run_convo(message: cl.Message):
    msg = cl.Message(content="")
    
    inputs = [HumanMessage(content=message.content)]

    config = {
        "configurable": {"thread_id": cl.user_session.get("chat_id")},
    }

    expert_events = ["InvokeExpertModel", "InitialRetrieval", "CreatePlan", "DataBaseHandler", "UserHandler", "HumanFeedback", "FeedbackHandler", "CalculationHandler", "LLMHandler", "OutputHandler"]
    documentSearchStep_cache = None
    expertModelStep_cache = None
    contextRetrievalStep_cache = None
    createPlanStep_cache = None
    databaseHandlerStep_cache = None
    userHandlerStep_cache = None
    llmHandlerStep_cache = None
    calculationHandlerStep_cache = None
    humanFeedback = False
    user_input = ""

    await handle_graph_events(graph, inputs, config, msg, expert_events, documentSearchStep_cache, expertModelStep_cache, contextRetrievalStep_cache, createPlanStep_cache, databaseHandlerStep_cache, userHandlerStep_cache, llmHandlerStep_cache, calculationHandlerStep_cache, humanFeedback, user_input)

async def handle_graph_events(graph, inputs, config, msg, expert_events, documentSearchStep_cache, expertModelStep_cache, contextRetrievalStep_cache, createPlanStep_cache, databaseHandlerStep_cache, userHandlerStep_cache, llmHandlerStep_cache, calculationHandlerStep_cache, humanFeedback, user_input):
    if inputs is not None:
        inputs = {"messages": inputs}

    async for event in graph.astream_events(inputs, config=config, version="v2"):
        if event["event"] == "on_chat_model_stream" and event['metadata'].get('langgraph_node','') == "agent":
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
                    async with documentSearchStep_cache as documentSearchStep:
                        output_dict = {'output': event["data"]["output"].content}
                        documentSearchStep.output = output_dict
                        await documentSearchStep.update()
                print("Event type: " + str(event["event"]) + " Event data: " + str(event["data"]))
        if event['metadata'].get('langgraph_node','') == "GetHelp" and event["event"] == "on_chain_stream":
            content = event["data"]
            await msg.send()
            await msg.stream_token(content['chunk']['messages'][0].content)
        if event['metadata'].get('langgraph_node','') in expert_events:
            if event['metadata'].get('langgraph_node','') == "InvokeExpertModel" and expertModelStep_cache is None:
                async with cl.Step(name="Expert") as expertModelStep:
                    expertModelStep_cache = expertModelStep
                    input = event['data']
                    task = event["data"]["input"]["messages"][-1].tool_calls[0]["args"]['task']
                    expertModelStep.input = {'task': task}
            else:
                async with expertModelStep_cache as expertModelStep:
                    if event['metadata'].get('langgraph_node','') == "InitialRetrieval" and event["event"] == "on_chat_model_end":
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
                            user_input = res['output']
                            userHandlerStep.input = res['output']
                            await userHandlerStep.update()
                    if event['metadata'].get('langgraph_node','') == "HumanFeedback" and event["event"] == "on_chain_end":
                        if humanFeedback == False:
                            humanFeedback = True
                        else:
                            user_feedback = [HumanMessage(content=user_input)]
                            graph.update_state(config, {"messages": user_feedback}, as_node="HumanFeedback")


                    if event['metadata'].get('langgraph_node','') == "LLMHandler":
                        if event['event'] == 'on_chat_model_start':
                            with cl.Step(name="LLMHandler") as llmHandlerStep:
                                llmHandlerStep_cache = llmHandlerStep
                                step_input = event['data']['input']['messages'][0][0].content
                                llmHandlerStep.input = step_input
                                await llmHandlerStep.update()
                        
                        elif event['event'] == 'on_chat_model_stream':
                            with llmHandlerStep_cache as llmHandlerStep:
                                chunk = event['data']["chunk"].content
                                await llmHandlerStep.stream_token(chunk)

                    
                    if event['metadata'].get('langgraph_node','') == "CalculationHandler":
                        if event['event'] == 'on_chain_end' and event['name'] == '_oai_structured_outputs_parser':
                            with cl.Step(name="CalculationHandler") as calculationHandlerStep:
                                calculationHandlerStep_cache = calculationHandlerStep
                                step_input = event['data']['output'].problem_plain_text
                                calculationHandlerStep.input = step_input
                                await calculationHandlerStep.update()
                        
                        elif event['event'] == 'on_chain_end' and event['name'] == '_write' and ('output' in event['data']):
                            with calculationHandlerStep_cache as calculationHandlerStep:
                                step_output = event['data']['output']['step_results'][0].result
                                calculationHandlerStep.output = step_output
                                await calculationHandlerStep.update()

                        print('CalculationHandler Event: ' + event['event'] + ', Data: ' + str(event['data']))

                    if event['metadata'].get('langgraph_node','') == "OutputHandler" and event['event'] == 'on_chain_end' and event['name'] == '_oai_structured_outputs_parser':
                        with expertModelStep_cache as expertModelStep:
                            conclusion = event['data']['output'].conclusion
                            citations = event['data']['output'].citations
                            expertModelStep.output = {'conclusion': conclusion, 'references': citations}
                            await expertModelStep.update()
                            
                            cl.user_session.set("conclusion", {'conclusion': conclusion, 'references': citations})
                            
                await expertModelStep.update()

    if humanFeedback:
        humanFeedback = False
        await handle_graph_events(graph, None, config, msg, expert_events, documentSearchStep_cache, expertModelStep_cache, contextRetrievalStep_cache, createPlanStep_cache, databaseHandlerStep_cache, userHandlerStep_cache, llmHandlerStep_cache, calculationHandlerStep_cache, humanFeedback, user_input)
    await msg.update()

if __name__ == "__main__":
    from chainlit.cli import run_chainlit
    run_chainlit(__file__)