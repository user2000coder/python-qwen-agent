"""
BCOS Planner
Hybrid Rule + LLM Decision
"""

import json

from protocol import Action



class Planner:


    def __init__(self, llm):

        self.llm = llm



    # =====================================================
    # Main Planner
    # =====================================================

    def plan(self, history):


        if not history:

            return PlannerResult(

                Action.ANSWER,

                {}

            )


        question = history[-1]["content"]


        # ---------------------------------------------
        # Rule Engine
        # ---------------------------------------------

        if self.need_search(question):


            return PlannerResult(

                Action.SEARCH,

                {

                    "query":
                    question

                }

            )



        # ---------------------------------------------
        # LLM Planner
        # ---------------------------------------------

        messages = [

            {

                "role":"system",

                "content":
                """
Bạn là BCOS Planner.

Nhiệm vụ:
Chọn action phù hợp.

Không trả lời câu hỏi.


ACTION:

search:
- cần thông tin mới
- cần dữ liệu bên ngoài
- không chắc chắn


calculator:
- bài toán số học


file:
- đọc dữ liệu file


answer:
- kiến thức ổn định


Chỉ output JSON:


{
 "action":"answer",
 "parameters":{}
}

"""
            }

        ]


        messages.extend(history)


        try:


            response = self.llm.chat(

                messages

            )


            return self.parse(

                response

            )


        except Exception:


            return PlannerResult(

                Action.ANSWER,

                {}

            )



    # =====================================================
    # Search Rules
    # =====================================================

    def need_search(

        self,

        question

    ):


        q = question.lower()



        keywords = [


            # time

            "2024",
            "2025",
            "2026",
            "2027",
            "2028",


            # current

            "hiện tại",
            "hôm nay",
            "mới nhất",
            "latest",
            "update",


            # politics

            "tổng thống",
            "thủ tướng",
            "bầu cử",
            "chính phủ",


            # market

            "giá",
            "cổ phiếu",
            "bitcoin",
            "vàng",


            # news

            "tin tức",
            "sự kiện"


        ]



        for word in keywords:


            if word in q:

                return True



        return False



    # =====================================================
    # Parse JSON
    # =====================================================

    def parse(

        self,

        text

    ):


        try:


            # lấy JSON nếu model thêm text

            start = text.find("{")

            end = text.rfind("}") + 1


            data = json.loads(

                text[start:end]

            )


            action = Action(

                data.get(

                    "action",

                    "answer"

                )

            )


            return PlannerResult(

                action,

                data.get(

                    "parameters",

                    {}

                )

            )



        except Exception:


            return PlannerResult(

                Action.ANSWER,

                {}

            )





# =====================================================
# Planner Result
# =====================================================

class PlannerResult:


    def __init__(

        self,

        action,

        parameters

    ):


        self.action = action

        self.parameters = parameters