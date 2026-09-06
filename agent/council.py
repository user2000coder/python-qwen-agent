"""
BCOS Multi Agent Council
"""

from agents.fact_agent import FactAgent
from agents.critic_agent import CriticAgent
from agents.reasoning_agent import ReasoningAgent
from agents.evidence_agent import EvidenceAgent
from agents.judge_agent import JudgeAgent



class Council:


    def __init__(self, llm):


        self.llm = llm


        self.agents = [

            FactAgent(),

            CriticAgent(),

            ReasoningAgent(),

            EvidenceAgent()

        ]


        self.judge = JudgeAgent()



    # =====================================================
    # Run Council
    # =====================================================

    def run(

        self,

        question,

        evidence

    ):


        reports = []



        for agent in self.agents:


            prompt = agent.prompt(

                question,

                evidence

            )


            answer = self.llm.chat([

                {

                    "role":
                    "system",

                    "content":
                    prompt

                }

            ])


            reports.append({

                "agent":
                agent.role,


                "report":
                answer

            })



        # Judge

        judge_prompt = self.judge.prompt(

            question,

            reports

        )


        final = self.llm.chat([

            {

                "role":
                "system",

                "content":
                judge_prompt

            }

        ])


        return final