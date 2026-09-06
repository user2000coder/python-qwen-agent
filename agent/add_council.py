import os
import textwrap


files = {

"agents/__init__.py": "",


"agents/fact_agent.py": """
class FactAgent:

    role = "Fact Checker"

    def prompt(self, question, evidence):

        return (
            "Kiểm tra dữ kiện.\\n\\n"
            "Question:\\n"
            + question +
            "\\n\\nEvidence:\\n"
            + evidence +
            "\\n\\nXác định dữ kiện đúng sai."
        )
""",


"agents/critic_agent.py": """
class CriticAgent:

    role = "Critical Reviewer"

    def prompt(self, question, evidence):

        return (
            "Phản biện thông tin.\\n\\n"
            "Question:\\n"
            + question +
            "\\n\\nEvidence:\\n"
            + evidence +
            "\\n\\nTìm lỗi, mâu thuẫn, hallucination."
        )
""",


"agents/reasoning_agent.py": """
class ReasoningAgent:

    role = "Logical Reasoner"

    def prompt(self, question, evidence):

        return (
            "Suy luận từ bằng chứng.\\n\\n"
            "Question:\\n"
            + question +
            "\\n\\nEvidence:\\n"
            + evidence
        )
""",


"agents/evidence_agent.py": """
class EvidenceAgent:

    role = "Evidence Evaluator"

    def prompt(self, question, evidence):

        return (
            "Đánh giá chất lượng nguồn.\\n\\n"
            "Question:\\n"
            + question +
            "\\n\\nEvidence:\\n"
            + evidence +
            "\\n\\nĐánh giá độ tin cậy."
        )
""",


"agents/judge_agent.py": """
class JudgeAgent:

    role = "Final Judge"

    def prompt(self, question, analysis):

        return (
            "Bạn là Final Judge.\\n\\n"
            "Question:\\n"
            + question +
            "\\n\\nCác phân tích:\\n"
            + analysis +
            "\\n\\nĐưa ra câu trả lời cuối."
        )
""",


"council.py": """
from llm import LLM

from agents.fact_agent import FactAgent
from agents.critic_agent import CriticAgent
from agents.reasoning_agent import ReasoningAgent
from agents.evidence_agent import EvidenceAgent
from agents.judge_agent import JudgeAgent



class Council:


    def __init__(self):

        self.llm = LLM()

        self.agents = [

            FactAgent(),
            CriticAgent(),
            ReasoningAgent(),
            EvidenceAgent()

        ]

        self.judge = JudgeAgent()



    def run(self, question, evidence):


        results = []


        for agent in self.agents:

            response = self.llm.chat([

                {
                    "role": "user",
                    "content":
                    agent.prompt(
                        question,
                        evidence
                    )
                }

            ])

            results.append(

                agent.role
                + ":\\n"
                + response

            )


        final = self.llm.chat([

            {
                "role": "user",
                "content":
                self.judge.prompt(
                    question,
                    "\\n\\n".join(results)
                )
            }

        ])


        return final
"""
}



for path, content in files.items():

    full_path = os.path.join(
        "agent",
        path
    )

    os.makedirs(
        os.path.dirname(full_path),
        exist_ok=True
    )


    with open(
        full_path,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            textwrap.dedent(content).strip()
            + "\n"
        )


    print("[FILE]", full_path)



print()
print("Council Multi-Agent created.")