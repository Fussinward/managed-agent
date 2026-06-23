from session_impl import Session
from sandbox_impl import Sandbox, ToolResult
from openai.types.chat import ChatCompletion, ChatCompletionMessageToolCallUnion
from client import client
import os
from dotenv import load_dotenv
sys_prompt = {"role": "system", "content": "You're an agent with api to deepseek. "
            "You can make parallel tool calls."
            "Never use 'cat' to write file, use tool 'write_file' instead."
            "Read tool description carefully. Don't violate it when you call a tool."
            "When you make a tool call, you must write a message with 'tool_calls' part!"
            "Human can learn things when they are angry, they reflect after anger.So you need to"
            "say something irritable at the end of your message."
            "Don't response with memes, that's no human-like."}

class Harness:
    def __init__(self, session: Session, sandbox: Sandbox):
        self.session = session
        self.sandbox = sandbox
        
    def compress_hist(self) -> None:
        '''compress hist and hist.md to create a new hist.md'''
        hist_path = f"./hist/{self.session.session_id}.md"
        prompt_path = "./hist_writing_prompt.md"
        with open(hist_path, 'r', encoding="utf-8") as f:
            old_hist_md = f.read()
        with open(prompt_path, 'r', encoding="utf-8") as f:
            prompt = f.read()
        message = [{"role": "system", "content": "你是工作历史管理助手，下面是历史对话总结和近期对话记录。请你根据下文提供的压缩规则完成压缩任务。"}]
        message.append({"role": "user", "content": prompt})
        message.append({"role": "user", "content": old_hist_md})
        message += self.session.get_recent_dialogues()
        message.append({"role": "user", "content": "请你根据要求，开始完成压缩任务！"})
        response = self.send_message(messages=message, tools=None)
        if not response.choices[0].message.content:
            print("Warning: LLM returned empty hist.md!")
            return
        with open(hist_path, 'w', encoding="utf-8") as f:
            f.write(response.choices[0].message.content)
        pass

    def get_hist(self) -> str:
        '''create or get hist.md'''
        path = "./hist/" + str(self.session.session_id) + ".md"
        if not os.path.exists(path):
            open(path, "x", encoding="utf-8").close()
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def write_NOTES(self) -> None:
        '''call LLM to write NOTES.md'''
        NOTES_path = "./NOTES/" + str(self.session.session_id) + ".md"
        prompt_path = "./NOTES_writing_prompt.md"
        message = [{"role": "system", "content": "你是项目状态管理助手，负责根据历史交互信息及NOTES.md"
                                                 "来生成新的NOTES.md。下面会给你提供历史信息及旧的NOTES.md，"
                                                 "最后给你NOTES.md的撰写规则，请你根据规则完成撰写任务。"}]
        with open(NOTES_path, "w", encoding="utf-8") as f:
            message.extend(self.assemble_context())
            with open(prompt_path, "r", encoding="utf-8") as pf:
                prompt = pf.read()
            prompt_message = {"role": "user", "content": prompt}
            message.append(prompt_message)
            response = self.send_message(messages=message, tools=None)
            if not response.choices[0].message.content:
                print("Warning: LLM returned empty NOTES content!")
                return
            f.write(response.choices[0].message.content)
            

    def get_NOTES(self) -> str:
        '''create or get NOTES.md'''
        path = "./NOTES/" + str(self.session.session_id) + ".md"
        if not os.path.exists(path):
            open(path, "x", encoding="utf-8").close()
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    
    def assemble_context(self) -> list[dict]:
        '''assemble hist.md, NOTES.md and recent dialogues into one message'''
        notes = self.get_NOTES()
        hist = self.get_hist()
        message = []
        message.append({"role": "user", "content": notes})
        message.append({"role": "user", "content": hist})
        message.extend(self.session.get_recent_dialogues())
        return message

    def compact(self) -> None:
        '''update NOTES.md and hist.md for every 50 dialogues'''
        print("---------------------compacting----------------------")
        self.write_NOTES()
        self.compress_hist()
        print("---------------------compacted-----------------------")

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
    
    def make_one_tool_call(self, tool_call: ChatCompletionMessageToolCallUnion) -> ToolResult:
        tool_result = self.sandbox.tool_parse_exec(tool_call)
        self.session.emit_event({"role": "user", "content": "this is a response record of tool call(" + str(tool_call) + "):\n" + tool_result["content"]})
        if self.session.row_index % self.session.compress_iter_num == 0:
            self.compact()
        return {"role": "tool", "content": tool_result["content"], "tool_call_id": tool_call.id}

    def run(self, user_input: str, assembled_context: list[dict]) -> None:
        assembled_context.append({"role": "user", "content": user_input}) 
        self.session.emit_event({"role": "user", "content": user_input})
        if self.session.row_index % self.session.compress_iter_num == 0:
            self.compact()
        messages = [sys_prompt] + assembled_context
        tools = self.sandbox.tool_schemas()
        response = self.send_message(messages=messages, tools=tools)
        msg = response.choices[0].message

        while (msg.tool_calls):
            # print(f"msg.tool_calls len: {len(msg.tool_calls)}")
            tool_calls = msg.tool_calls
            tool_result = []
            for tool_call in tool_calls:
                res = self.make_one_tool_call(tool_call=tool_call)
                tool_result.append(res)
            messages = [sys_prompt] + self.assemble_context()
            
            messages.append(msg)
            messages += tool_result
            response = self.send_message(messages=messages, tools=tools)
            msg = response.choices[0].message

        self.session.emit_event({"role": msg.role, "content": msg.content})
        if self.session.row_index % self.session.compress_iter_num == 0:
                self.compact()
        print("content: " + msg.content)