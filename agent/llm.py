"""
BCOS Ollama LLM Wrapper
"""

import os

import ollama

from config import (
    MODEL,
    OLLAMA_HOST,
    TEMPERATURE
)



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


        path = "prompts/bcos.txt"


        if os.path.exists(path):


            with open(

                path,

                "r",

                encoding="utf-8"

            ) as f:


                return f.read()



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