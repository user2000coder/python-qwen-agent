"""
BCOS Tool Protocol
"""

from enum import Enum


# =====================================================
# Available Actions
# =====================================================

class Action(str, Enum):


    SEARCH = "search"


    CALCULATOR = "calculator"


    FILE = "file"


    ANSWER = "answer"



# =====================================================
# Tool Call Object
# =====================================================

class ToolCall:


    def __init__(
        self,
        action,
        parameters=None
    ):


        self.action = action


        self.parameters = (
            parameters
            if parameters
            else {}
        )



    def to_dict(self):


        return {

            "action":
                self.action.value,


            "parameters":
                self.parameters

        }



    def __repr__(self):


        return (

            f"ToolCall("
            f"{self.action}, "
            f"{self.parameters}"
            f")"

        )