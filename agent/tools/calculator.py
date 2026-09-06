"""
BCOS Calculator Tool
Safe Math Evaluation
"""

import ast
import operator



class CalculatorTool:


    name = "calculator"



    # Các phép toán được phép

    operators = {


        ast.Add:
            operator.add,


        ast.Sub:
            operator.sub,


        ast.Mult:
            operator.mul,


        ast.Div:
            operator.truediv,


        ast.Pow:
            operator.pow,


        ast.USub:
            operator.neg

    }



    # =====================================================
    # Run
    # =====================================================

    def run(
        self,
        expression
    ):


        try:


            result = self.calculate(

                expression

            )


            return {


                "success":
                    True,


                "expression":
                    expression,


                "result":
                    result,


                "confidence":
                    "high"

            }



        except Exception as e:


            return {


                "success":
                    False,


                "expression":
                    expression,


                "error":
                    str(e)

            }



    # =====================================================
    # Safe Parser
    # =====================================================

    def calculate(
        self,
        expression
    ):


        tree = ast.parse(

            expression,

            mode="eval"

        )


        return self._eval(

            tree.body

        )



    def _eval(
        self,
        node
    ):


        if isinstance(

            node,

            ast.Constant

        ):

            if isinstance(

                node.value,

                (
                    int,
                    float

                )

            ):

                return node.value



        if isinstance(

            node,

            ast.BinOp

        ):


            left = self._eval(

                node.left

            )


            right = self._eval(

                node.right

            )


            op = self.operators.get(

                type(node.op)

            )


            if op:

                return op(

                    left,

                    right

                )



        if isinstance(

            node,

            ast.UnaryOp

        ):


            op = self.operators.get(

                type(node.op)

            )


            if op:

                return op(

                    self._eval(

                        node.operand

                    )

                )



        raise ValueError(

            "Unsupported expression"

        )