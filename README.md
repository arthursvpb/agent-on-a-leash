<div align="center">
  <h1>Agent on a Leash</h1>
  <p>A support agent for damaged orders. Python reads the price from the order record. A person reviews refunds over $150.</p>
  <p>
    <img alt="Python 3.11+" src=".github/assets/python.svg">
    <img alt="LangChain: interpretation" src=".github/assets/langchain.svg">
    <img alt="LangGraph: workflow" src=".github/assets/langgraph.svg">
    <img alt="LangSmith: evaluation" src=".github/assets/langsmith.svg">
  </p>
</div>

## Run the demo

With uv or Python 3.11+, run `make setup && make demo`. Watch the $420 refund pause for review before the customer sees an approved amount.

![Terminal recording of five offline support tickets, including a $420 refund that resumes after a reviewer approves it.](.github/assets/demo.gif)

## System design

![Refund workflow for order A1003. LangChain extracts a request, LangGraph pauses the $420 refund for review, and LangSmith can trace the decision.](.github/assets/system-design.svg)

## Follow one ticket

| Library | Where it applies |
| --- | --- |
| [LangChain](src/classifier.py) | Turns “A1003 arrived cracked” into a validated damage report. The offline demo uses rules for this step. |
| [LangGraph](src/graph.py) | Looks up A1003 and runs the refund policy. At $420 it saves the thread, waits for a reviewer, then resumes to send the reply. |
| [LangSmith](evals/run_langsmith.py) | Shows which rule fired in a ticket trace. Its hosted experiment scores the same eight cases as the local eval. |

## Try it yourself

Try `make chat` as `ana@example.com` with **“A1003 arrived cracked. Refund please.”** Run `make check` for lint, types and all eight eval cases.

For a live model, copy `.env.example` to `.env`, set `CLASSIFIER=llm` and supply your provider key. Enable `LANGSMITH_TRACING=true` with a LangSmith key to see traces. [Configuration](.env.example)
