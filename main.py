from sandbox_impl import Sandbox
from session_impl import Session
from harness_impl import Harness

session_id = Session.select_session_id()
session = Session(session_id=session_id)
sandbox = Sandbox(session_id=session_id)
agent = Harness(session=session, sandbox=sandbox)
while True:
    user_message = input("user input:")
    assembled_context = agent.assemble_context()
    agent.run(user_input=user_message, assembled_context=assembled_context)