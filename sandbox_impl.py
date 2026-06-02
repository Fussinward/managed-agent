import subprocess
from openai.types.chat import ChatCompletionMessageToolCallUnion
import json
from typing import TypedDict
from session_impl import Session

class ToolResult(TypedDict):
    role: str
    tool_call_id: str
    content: str


class Sandbox:
    def __init__(self, session_id: int):
        self.session_id = session_id
        self.container_id = Session.get_container_id(session_id=self.session_id)
        self.provision()
        pass

    def provision(self) -> None:
        if self.container_id:
            '''有容器，直接启动'''
            res = subprocess.run(
                ["docker", "start", self.container_id],
                capture_output=True, text=True
            )
            if res.returncode == 0:
                return
        '''没容器，创建一个'''
        res = subprocess.run("docker run -d python:alpine sleep infinity", capture_output=True, shell=True, text=True)
        self.container_id = res.stdout.strip()
        Session.change_container_id(session_id=self.session_id, new_container_id=self.container_id)

    def tool_schemas(self) -> list[dict]:
        shell_tool = {
            "type": "function",
            "function": {
                "name": "execute_shell",
                "description": "interact with a python:alpine container using one shell command, return shell outputs."
                               "MUST use write_file tool to write files instead of cat in shell!!!",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "the shell command to be executed. If you"
                        "need to install python package, switch source to https://pypi.tuna.tsinghua.edu.cn/simple/"}
                    },
                    "required": ["command"],
                    "additionalProperties": False
                },
            },
        }
        provision_tool = {
            "type": "function",
            "function": {
                "name": "provision",
                "description": "create a new sandbox, must call 'close' before 'provision'",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False
                },
            },
        }
        close_tool = {
            "type": "function",
            "function": {
                "name": "close",
                "description": "remove the current sandbox, must call 'provision' after this",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False
                },
            },
        }
        write_file_tool = {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Write file to path.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                    "required": ["path", "content"],
                    "additionalProperties": False
                },
            },
        }
        export_file_tool = {
            "type": "function",
            "function": {
                "name": "export_file",
                "description": "Export project file to host machine. Don't call unless user has explicitly specified to export files.",
                "parameters": {
                    "type": "object",
                    "properties": {"sbx_prjt_root": {"type": "string", "description": "root path of the project"},
                                   "project_name": {"type": "string", "description": "name of the project, make up a name if not exists"}},
                    "required": ["sbx_prjt_root", "project_name"],
                    "additionalProperties": False
                },
            },
        }
        return [shell_tool, provision_tool, close_tool, write_file_tool, export_file_tool]

    def tool_parse_exec(self, tool_calls: ChatCompletionMessageToolCallUnion) -> ToolResult:
        schemas = self.tool_schemas()
        flag = False
        for tool in schemas:
            if tool["function"]["name"] == tool_calls.function.name:
                flag = True
                break
        if not flag:
            raise NameError

        print("tool call: " + tool_calls.function.name)

        if tool_calls.function.name == 'close':
            self.close()
            res: ToolResult = {"role": "tool", "tool_call_id": tool_calls.id, "content": "done"}

        elif tool_calls.function.name == 'provision':
            self.provision()
            res: ToolResult = {"role": "tool", "tool_call_id": tool_calls.id, "content": "done"}

        elif tool_calls.function.name == 'execute_shell':
            args = json.loads(tool_calls.function.arguments)
            output = self.execute_shell(command=args["command"])
            res: ToolResult = {"role":"tool", "tool_call_id": tool_calls.id, "content": output}

        elif tool_calls.function.name == 'write_file':
            args = json.loads(tool_calls.function.arguments)
            self.write_file(path=args["path"], content=args["content"])
            res: ToolResult = {"role":"tool", "tool_call_id": tool_calls.id, "content": "done"}
        
        elif tool_calls.function.name == 'export_file':
            args = json.loads(tool_calls.function.arguments)
            self.export_file(sbx_prjt_root=args["sbx_prjt_root"], project_name=args["project_name"])
            res: ToolResult = {"role":"tool", "tool_call_id": tool_calls.id, "content": "done"}
 
        return res
    
    def execute_shell(self, command: str) -> str:
        print("executing: " + command)
        process = subprocess.run(
            ["docker", "exec", self.container_id, "sh", "-c", command],
            capture_output=True, text=True, encoding="utf-8"
        )
        res = process.stdout + process.stderr
        print(res)
        return res
    
    def write_file(self, path: str, content: str) -> None:
        import os
        parent = os.path.dirname(path)
        # 先创建父目录
        subprocess.run(
            ["docker", "exec", self.container_id, "mkdir", "-p", parent],
            capture_output=True
        )
        proc = subprocess.Popen(
            ["docker", "exec", "-i", self.container_id, "sh", "-c", f"cat > {path}"],
            stdin=subprocess.PIPE, text=True, encoding="utf-8"
        )
        proc.communicate(content)

    def close(self) -> None:
        command = "docker rm -f " + self.container_id
        self.container_id = None
        subprocess.run(command, shell=True)
    
    def export_file(self, sbx_prjt_root: str, project_name: str) -> None:
        '''export project file to host machine'''
        import os
        print(f"current working directory: {os.getcwd()}")
        host_dest = f"./{project_name}/"
        result = subprocess.run(
            ["docker", "cp", "-L", f"{self.container_id}:{sbx_prjt_root}", host_dest],
            capture_output=True, text=True
        )

        print(result.stderr, result.stdout)