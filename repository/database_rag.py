import os
from langchain_community.tools.sql_database.tool import (
    ListSQLDatabaseTool,
    InfoSQLDatabaseTool,
    QuerySQLDataBaseTool,
    QuerySQLCheckerTool,
)
from sqlalchemy import create_engine
from langchain_community.agent_toolkits import SQLDatabaseToolkit

# from langchain_community.chat_models import ChatOllama

from langchain_ollama import ChatOllama
from langchain_experimental.llms.ollama_functions import OllamaFunctions

from langchain.agents import AgentExecutor, initialize_agent
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage
from langchain_community.utilities import SQLDatabase
from langchain_core.prompts import ChatPromptTemplate
from langchain.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from langchain.chains import LLMChain
from langchain_openai import ChatOpenAI
from langchain import hub

# from langchain_core.runnables import RunnableSequence
from langchain.chains import create_sql_query_chain

from lib.helpers import (
    format_columns_and_foreign_keys,
    get_columns_and_foreign_keys,
    get_foreign_keys,
)
from tools.database import ExplanatorTool, QueryCheckerTool, QueryTool, SchemaTool

SQLALCHEMY_DATABASE_URL = os.environ["SQLALCHEMY_DATABASE_URL"]
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


class DatabaseAgentRag:

    _database_uri = SQLALCHEMY_DATABASE_URL
    _db = SQLDatabase.from_uri(database_uri=_database_uri)

    _formatted_output = format_columns_and_foreign_keys()
    _system_message = SystemMessage(
        content="""You are an agent designed to interact with a SQL database.
    Then, Given an input question, create a syntactically correct Postgresql query to run, then look at the results of the query and return the answer.
    Unless the user specifies a specific number of examples they wish to obtain, always limit your query to at most 5 results.
    Never query for all the columns from a specific table, only ask for the relevant columns given the question.
    Remember, table names always starts with public in postgres (e.g. public.libraries).
    You have access to tools for interacting with the database.
    You MUST double check your query before executing it. If you get an error while executing a query, rewrite the query and try again.
    DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.) to the database.
    To start you should ALWAYS look at the tables in the database to see what you can query.
    Do NOT skip this step.
    Then you SHOULD query the schema of the most relevant tables.
    """
    )

    _llm = ChatOllama(model="llama3.1")

    _toolkit = SQLDatabaseToolkit(db=_db, llm=_llm)

    _tools = _toolkit.get_tools()

    _llm = _llm.bind_tools(_tools)

    # _prompt_template = hub.pull("langchain-ai/sql-agent-system-prompt").format(
    #     dialect="Postgres", top_k=5
    # )

    _agent_executor = create_react_agent(
        _llm,
        _tools,
        state_modifier=_system_message,
    )

    input_query = "How many events in event table?"

    @classmethod
    def execute(self):

        # response = self._agent_executor.invoke(
        #     {"messages": "How many events will happen in november 2023?"},
        #     {"recursion_limit": 40},
        # )
        # print(response)
        # re = get_schema()

        # print(de)
        print(self._db)
        # print(self._formatted_output)


class DatabaseChainRag:
    _database_uri = SQLALCHEMY_DATABASE_URL
    _db = SQLDatabase.from_uri(database_uri=_database_uri)

    # _engine = create_engine(_database_uri)

    _llm = ChatOllama(model="llama3")

    _prompt_template = PromptTemplate(
        input_variables=["question"],
        template="Question: {question}\nSQL query: ",
    )

    input_query = "How many events in event table?"

    chain = create_sql_query_chain(_llm, _db)

    @classmethod
    def execute(self):
        # print(self._toolkit, "_toolkit")
        # print(self._tools, "_tools")
        # print(self._llm, "_llm")
        # print(self._llm_chain, "_llm_chain")
        # print(self._agent, "_agent")
        # return
        # print(self._tools, "toools")
        # print(self._agent_executor, "_agent_executor")
        # print(self._toolkit, "toolkits")
        # response = self.chain.invoke({"question": self.input_query})
        # print(self._db.get_usable_table_names())
        print(self._db.get_context())
        # print(response)


class SQLDatabaseAgent:
    def __init__(self, database_uri):
        self.db = SQLDatabase.from_uri(database_uri=database_uri)
        # self.llm = ChatOllama(model="llama3.1", temperature=0.2)
        self.llm = ChatOpenAI(model="gpt-4o-mini", api_key=OPENAI_API_KEY)

        self.schema_tool = SchemaTool(db=self.db)
        self.query_tool = QueryTool(llm=self.llm)
        self.query_checker_tool = QueryCheckerTool(llm=self.llm, db=self.db)
        self.explanator_tool = ExplanatorTool(
            llm=self.llm,
        )

        self.max_iterations = 5

    def execute(self, question: str):
        schema_info, table_names = self.schema_tool.run({})
        iteration = 0
        last_error = ""

        while iteration < self.max_iterations:
            iteration += 1
            sql_query = self.query_tool.run(
                {
                    "question": question,
                    "schema_info": schema_info,
                    "tables": table_names,
                    "error": last_error,
                }
            )
            # print("\nGenerated SQL Query:")
            # print(sql_query)

            query_result = self.query_checker_tool.run({"query": sql_query})

            if "Error:" not in query_result:
                # print("\nQuery executed successfully.")
                # print(query_result)
                final_result = self.explanator_tool.run(
                    {"question": question, "sql_query_result": query_result}
                )
                print(final_result)
                return final_result

            else:
                last_error = query_result
                print("\nQuery failed. Retrying...")

        print(
            f"\nMax iterations reached ({self.max_iterations}). Last error: {last_error}"
        )
        return last_error
