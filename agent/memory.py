"""
BCOS Memory System
"""

import json

import log

from paths import HISTORY_DIR


LOGGER = log.get(
    "memory"
)



class Memory:


    FILE = HISTORY_DIR / "conversation.json"


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


        HISTORY_DIR.mkdir(

            parents=True,

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


        if self.FILE.exists():


            try:

                with open(

                    self.FILE,

                    "r",

                    encoding="utf-8"

                ) as f:


                    self.data = json.load(f)



            except (
                OSError,
                ValueError,
            ):


                # Resetting silently is indistinguishable from a
                # first run, so say which file was unreadable.

                LOGGER.warning(
                    "could not read %s; "
                    "starting with empty memory",
                    self.FILE,
                    exc_info=True
                )

                self.data = []
