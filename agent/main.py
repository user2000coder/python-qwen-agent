"""
BCOS Agent CLI

Run as a script:

    python agent/main.py

The BCOS modules import each other flat ("from llm import LLM"),
so the source directory has to be on sys.path. Adding it here
makes the CLI launchable from any working directory instead of
only from inside agent/.
"""

import os
import sys


sys.path.insert(
    0,
    os.path.dirname(
        os.path.abspath(
            __file__
        )
    )
)


import log

from agent import Agent


LOGGER = log.get(
    "repl"
)



def banner():

    print("=" * 60)

    print(
        "BCOS Agent"
    )

    print(
        "Qwen2.5:3B + Tool + Council"
    )

    print(
        "Gõ 'exit' để thoát."
    )

    print("=" * 60)



def main():


    banner()


    agent = Agent()



    while True:


        try:


            question = input(
                "\nBạn: "
            ).strip()



            if not question:

                continue



            if question.lower() in [

                "exit",

                "quit",

                "q"

            ]:

                print(
                    "Bye!"
                )

                break



            print(
                "\nBCOS > ",
                end="",
                flush=True
            )



            for token in agent.ask(

                question

            ):


                print(

                    token,

                    end="",

                    flush=True

                )



            print()



        except EOFError:


            # stdin closed (piped input, non-interactive run).
            #
            # Without this branch the generic Exception handler
            # below swallows EOFError and the loop spins forever.

            print(

                "\n\nHết input. Bye!"

            )

            break



        except KeyboardInterrupt:


            print(

                "\n\nĐã dừng."

            )

            break



        except Exception as e:


            # str(e) alone gave no file or line, which is how a
            # TypeError in the planner could be reported only as
            # "Qwen cannot search". The traceback goes to
            # agent/logs/agent.log.

            LOGGER.exception(

                "unhandled error answering %r",

                question

            )


            print(

                "\n❌ ERROR:",

                e

            )


            print(

                "   (traceback đã ghi vào "
                "agent/logs/agent.log)"

            )





if __name__ == "__main__":

    main()