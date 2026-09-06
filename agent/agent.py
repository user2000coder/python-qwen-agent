"""
BCOS Agent Core
"""

import json

from llm import LLM
from planner import Planner
from memory import Memory
from protocol import Action

from config import MAX_TOOL_ITERATIONS

from council import Council

from tools.search import SearchTool
from tools.calculator import CalculatorTool
from tools.file import FileTool



class Agent:



    def __init__(self):


        self.llm = LLM()


        self.memory = Memory()


        self.planner = Planner(

            self.llm

        )


        self.council = Council(

            self.llm

        )


        self.tools = {


            Action.SEARCH:
            SearchTool(),


            Action.CALCULATOR:
            CalculatorTool(),


            Action.FILE:
            FileTool()

        }



    # =====================================================
    # Ask
    # =====================================================

    def ask(

        self,

        question

    ):


        self.memory.add(

            "user",

            question

        )


        history = self.memory.messages()



        evidence = []



        # ==========================================
        # Planner
        # ==========================================

        call = self.planner.plan(

            history

        )



        print(

            "\n🧠 Planner: phân tích..."

        )


        print(

            "🧠 Action:",

            call.action.value

        )



        # ==========================================
        # Tool
        # ==========================================

        if call.action in self.tools:


            print(

                "🌐 Tool đang chạy..."

            )


            result = self.tools[

                call.action

            ].run(

                **call.parameters

            )


            evidence.append(result)



            print(

                "✅ Tool hoàn tất"

            )



        else:


            evidence.append({

                "message":

                "No external tool used."

            })



        # ==========================================
        # Council ALWAYS runs
        # ==========================================


        print(

            "\n🤖 Council: 5 AI đang suy luận..."

        )



        result = self.council.run(

            question,

            json.dumps(

                evidence,

                ensure_ascii=False,

                indent=2

            )

        )



        answer = result



        yield answer



        self.memory.add(

            "assistant",

            answer

        )