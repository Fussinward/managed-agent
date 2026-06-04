from session_impl import Session
from sandbox_impl import Sandbox
from openai.types.chat import ChatCompletion
from client import client
import os
from dotenv import load_dotenv
sys_prompt = {"role": "system", "content": "You're an agent with api to deepseek. You can make tool call just one at a time."
"Never use cat to write file, use tool 'write_file' instead."
"Read tool description carefully. Don't violate it when you call a tool."}

class Harness:
    def __init__(self, session: Session, sandbox: Sandbox):
        self.session = session
        self.sandbox = sandbox
        
    def compress_hist(self, hist: list[dict]) -> None:
        '''compress hist and hist.md to create a new hist.md'''
        pass

    def get_hist(self) -> str:
        '''create or get hist.md'''

    def write_NOTES(self) -> None:
        '''call LLM to write NOTES.md'''
        pass

    def get_NOTES(self) -> str:
        '''create or get NOTES.md'''
        pass
    
    def assemble_context(self) -> list[dict]:
        '''assemble hist.md, NOTES.md and recent dialogues into one message'''

    def compact(self) -> None:
        '''update NOTES.md and hist.md for every 50 dialogues'''

    def send_message(self, messages, tools) -> ChatCompletion:
        load_dotenv()
        response: ChatCompletion = client.chat.completions.create(
            model=os.getenv("model"),
            messages=messages,
            tools=tools,
            stream=False,
            reasoning_effort="low",
            extra_body={"thinking": {"type": "enabled"}}
        )
        return response
    
    def run(self, user_input: str, hist: list[dict]) -> None:
        hist.append({"role": "user", "content": user_input}) 
        self.session.emit_event({"role": "user", "content": user_input})
        messages = [sys_prompt] + hist
        tools = self.sandbox.tool_schemas()
        response = self.send_message(messages=messages, tools=tools)
        msg = response.choices[0].message
        while msg.tool_calls:
            tool_calls = msg.tool_calls[0]
            if msg.reasoning_content:
                print("reasoning content: " + msg.reasoning_content)
            self.session.emit_event({"role": msg.role, "content": str(tool_calls)})
            messages.append(msg)

            tool_result = self.sandbox.tool_parse_exec(tool_calls)
            self.session.emit_event({"role": "user", "content": tool_result["content"]})
            messages.append({"role": "tool", "content": tool_result["content"], "tool_call_id": tool_calls.id})
            response = self.send_message(messages=messages, tools=tools)
            msg = response.choices[0].message

        self.session.emit_event({"role": msg.role, "content": msg.content})
        print("content: " + msg.content)