"""
BCOS Agent CLI
"""

from agent import Agent



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



        except KeyboardInterrupt:


            print(

                "\n\nĐã dừng."

            )

            break



        except Exception as e:


            print(

                "\n❌ ERROR:",

                e

            )





if __name__ == "__main__":

    main()