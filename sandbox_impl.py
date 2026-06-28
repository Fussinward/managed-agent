import subprocess
from openai.types.chat import ChatCompletionMessageToolCallUnion
import json
from typing import TypedDict
from session_impl import Session
import threading

class ToolResult(TypedDict):
    role: str
    tool_call_id: str
    content: str

class Sandbox:
    def __init__(self, session_id: int):
        self.session_id = session_id
        self.container_id = Session.get_container_id(session_id=self.session_id)
        self.provision()
        self._running = {} # pid → (process, out_buf, err_buf, done_event)
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
        res = subprocess.run("docker run -d python:3.11-slim sleep infinity", capture_output=True, shell=True, text=True)
        self.container_id = res.stdout.strip()
        Session.change_container_id(session_id=self.session_id, new_container_id=self.container_id)

    def tool_schemas(self) -> list[dict]:
        shell_tool = {
            "type": "function",
            "function": {
                "name": "execute_shell",
                "description": "interact with a python container using one shell command, return shell outputs.If you"
                        "need to install python package, switch source to https://pypi.tuna.tsinghua.edu.cn/simple/!!!"
                               "MUST use write_file tool to write files instead of cat in shell!!!"
                               "Time-consuming command will return a pid(on host) to you, don't mess it up with pids in container!",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "the shell command to be executed."}
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

        wait_check_tool = {
            "type": "function",
            "function": {
                "name": "wait_check",
                "description": "Start to wait for a period of time for a running process on host machine."
                "Return info after waiting.",
                "parameters": {
                    "type": "object",
                    "properties": {"pid": {"type": "integer", "description": "the pid of process to wait. It's a process on host machine if you need to know."},
                                   "timeout": {"type": "integer", "description": "waiting seconds"}},
                    "required": ["pid", "timeout"],
                    "additionalProperties": False
                },
            },
        }

        kill_process_tool = {
            "type": "function",
            "function": {
                "name": "kill_process",
                "description": "Kill process with pid."
                "Return info after waiting.",
                "parameters": {
                    "type": "object",
                    "properties": {"pid": {"type": "integer", "description": "the pid of process to wait. It's a process on host machine if you need to know."}},
                    "required": ["pid"],
                    "additionalProperties": False
                },
            },
        }

        return [shell_tool, provision_tool, close_tool, write_file_tool, export_file_tool, wait_check_tool, kill_process_tool]

    def tool_parse_exec(self, tool_calls: ChatCompletionMessageToolCallUnion) -> ToolResult:
        schemas = self.tool_schemas()
        flag = False
        for tool in schemas:
            if tool["function"]["name"] == tool_calls.function.name:
                flag = True
                break
        if not flag:
            raise NameError

        print("\033[91mtool call:\033[0m " + tool_calls.function.name)

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

        elif tool_calls.function.name == 'wait_check':
            args = json.loads(tool_calls.function.arguments)
            output = self.wait_check(pid=args["pid"], timeout=args["timeout"])
            res: ToolResult = {"role":"tool", "tool_call_id": tool_calls.id, "content": output}
        
        elif tool_calls.function.name == 'kill_process':
            args = json.loads(tool_calls.function.arguments)
            flag = self.kill_process(pid=args["pid"])
            if flag: output = "done"
            else: output = "Failed, wrong pid!"
            res: ToolResult = {"role":"tool", "tool_call_id": tool_calls.id, "content": output}
 
        return res
    
    def execute_shell(self, command: str) -> str:
        print("executing: " + command)
        process = subprocess.Popen(
            ["docker", "exec", "-t", self.container_id, "sh", "-c", command], 
                encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        done = threading.Event()
        out_buf, err_buf = [], []
        
        self._running[process.pid] = (process, out_buf, err_buf, done)

        def reader(pipe, buf):
            while True:
                chunk = pipe.read(4096)
                if not chunk:
                    break
                buf.append(chunk)
            pipe.close()

        threading.Thread(target=reader, args=(process.stdout, out_buf), daemon=True).start()
        threading.Thread(target=reader, args=(process.stderr, err_buf), daemon=True).start()
        threading.Thread(target=lambda: (process.wait(), done.set()), daemon=True).start()

        if done.wait(timeout=10):
            del self._running[process.pid]
            res = ''.join(out_buf + err_buf)
        else:
            res = "\nProcess has run for 10s and hasn't finished yet. PID:" + str(process.pid)
        return res
        
    def wait_check(self, pid: int, timeout: int) -> str:
        if pid not in self._running:
            return "进程不存在！"
        proc, out_buf, err_buf, done = self._running[pid]
        print("wait at most: " + str(timeout) + " seconds")
        if done.wait(timeout=timeout):
            del self._running[pid]
            res = ''.join(out_buf + err_buf)
        else:
            res = "\nProcess has run for " + str(timeout) + " more seconds and hasn't finished yet. PID:" + str(pid)
        return res
    
    def kill_process(self, pid: int) -> bool:
        if pid not in self._running:
            return False
        proc, _, _, _ = self._running[pid]
        proc.terminate()
        del self._running[pid]
        return True
    
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
        host_dest = f"./exported/{project_name}/"
        result = subprocess.run(
            ["docker", "cp", "-L", f"{self.container_id}:{sbx_prjt_root}", host_dest],
            capture_output=True, text=True
        )

        print(result.stderr, result.stdout)