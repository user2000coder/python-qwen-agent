"""
BCOS Memory System
"""

import json
import os



class Memory:


    FILE = "history/conversation.json"


    MAX_MESSAGES = 10



    def __init__(self):


        self.data = []


        self.load()



    # =====================================
    # Add message
    # =====================================

    def add(
        self,
        role,
        content
    ):


        self.data.append({

            "role":
                role,

            "content":
                content

        })


        self.data = self.data[

            -self.MAX_MESSAGES:

        ]


        self.save()



    # =====================================
    # Get messages
    # =====================================

    def messages(self):


        return self.data.copy()



    # =====================================
    # Save
    # =====================================

    def save(self):


        os.makedirs(

            "history",

            exist_ok=True

        )


        with open(

            self.FILE,

            "w",

            encoding="utf-8"

        ) as f:


            json.dump(

                self.data,

                f,

                ensure_ascii=False,

                indent=2

            )



    # =====================================
    # Load
    # =====================================

    def load(self):


        if os.path.exists(

            self.FILE

        ):


            try:

                with open(

                    self.FILE,

                    "r",

                    encoding="utf-8"

                ) as f:


                    self.data = json.load(f)



            except:


                self.data = []