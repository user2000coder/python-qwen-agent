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


        # mkdir used the module-level HISTORY_DIR while the write
        # used self.FILE, so overriding Memory.FILE created the
        # wrong directory and then failed. Derive both from the
        # same place.

        try:


            self.FILE.parent.mkdir(

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


        except OSError:


            # Runtime paths now live next to the source tree, so a
            # read-only checkout (pip install, read-only mount,
            # container image) would otherwise fail the very first
            # question. Losing persistence is acceptable; refusing
            # to answer is not.

            LOGGER.warning(

                "could not write %s; "
                "conversation memory is not persisted",

                self.FILE,

                exc_info=True

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
