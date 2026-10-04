"""
BCOS Ollama LLM Wrapper
"""

import ollama

from config import (
    MODEL,
    OLLAMA_HOST,
    TEMPERATURE
)

from paths import PROMPTS_DIR



class LLM:



    def __init__(self):


        self.client = ollama.Client(

            host=OLLAMA_HOST

        )


        self.system_prompt = self.load_prompt()



    # =====================================================
    # Load BCOS Prompt
    # =====================================================

    def load_prompt(self):


        path = PROMPTS_DIR / "bcos.txt"


        if path.exists():


            return path.read_text(

                encoding="utf-8"

            )



        return """

Bạn là BCOS AI Agent.

Ưu tiên Evidence.
Không bịa dữ liệu.

"""



    # =====================================================
    # Add System Prompt
    # =====================================================

    def inject_system(

        self,

        messages

    ):


        return [

            {

                "role":
                "system",

                "content":
                self.system_prompt

            }

        ] + messages



    # =====================================================
    # Chat
    # =====================================================

    def chat(

        self,

        messages

    ):



        messages = self.inject_system(

            messages

        )


        response = self.client.chat(


            model=MODEL,


            messages=messages,


            options={


                "temperature":
                TEMPERATURE,


                "num_gpu":
                0


            }


        )


        return response[

            "message"

        ][

            "content"

        ]



    # =====================================================
    # Stream
    # =====================================================

    def stream(

        self,

        messages

    ):


        messages = self.inject_system(

            messages

        )


        response = self.client.chat(


            model=MODEL,


            messages=messages,


            stream=True,


            options={


                "temperature":
                TEMPERATURE,


                "num_gpu":
                0


            }

        )



        for chunk in response:


            content = (

                chunk

                .get(
                    "message",
                    {}
                )

                .get(
                    "content",
                    ""
                )

            )


            if content:


                yield content