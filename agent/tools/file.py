"""
BCOS File Tool
Safe File Reader
"""

import os
import json



class FileTool:


    name = "file"



    # Thư mục cho phép

    ALLOWED_DIR = "data"



    # =====================================================
    # Run
    # =====================================================

    def run(
        self,
        path
    ):


        try:


            full_path = self.validate_path(

                path

            )


            content = self.read_file(

                full_path

            )


            return {


                "success":
                    True,


                "file":
                    path,


                "content":
                    content,


                "confidence":
                    "high"

            }



        except Exception as e:


            return {


                "success":
                    False,


                "error":
                    str(e)

            }



    # =====================================================
    # Security
    # =====================================================

    def validate_path(
        self,
        path
    ):


        base = os.path.abspath(

            self.ALLOWED_DIR

        )


        target = os.path.abspath(

            path

        )



        if not target.startswith(

            base

        ):

            raise PermissionError(

                "File outside allowed directory"

            )



        if not os.path.exists(

            target

        ):

            raise FileNotFoundError(

                target

            )



        return target



    # =====================================================
    # Reader
    # =====================================================

    def read_file(
        self,
        path
    ):


        ext = os.path.splitext(

            path

        )[1].lower()



        if ext == ".json":


            with open(

                path,

                "r",

                encoding="utf-8"

            ) as f:


                return json.dumps(

                    json.load(f),

                    ensure_ascii=False,

                    indent=2

                )



        else:


            with open(

                path,

                "r",

                encoding="utf-8"

            ) as f:


                return f.read()