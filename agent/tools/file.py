"""
BCOS File Tool
Safe File Reader
"""

import os
import json

from paths import DATA_DIR



class FileTool:


    name = "file"



    # Thư mục cho phép
    #
    # Resolved against the BCOS source tree, not the process
    # working directory, so "data/x.txt" means the same file
    # no matter where BCOS was launched from.

    ALLOWED_DIR = DATA_DIR



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

    def resolve_target(
        self,
        path,
        base
    ):
        """
        Resolve a requested path to an absolute real path.

        A relative path is always resolved inside the allowed
        directory. A leading "data/" is accepted so callers can
        keep using the documented "data/example.txt" form.
        """

        requested = str(
            path
        ).strip()

        if os.path.isabs(
            requested
        ):
            return os.path.realpath(
                requested
            )

        normalized = requested.replace(
            "\\",
            "/"
        ).lstrip(
            "/"
        )

        # basename(realpath(...)) breaks when agent/data is a
        # symlink: the documented "data/x.txt" form then has to be
        # spelled with the link target's name instead. Take the
        # name from the UNRESOLVED directory.

        allowed_name = os.path.basename(
            str(
                self.ALLOWED_DIR
            ).rstrip(
                "/"
            )
        )

        prefix = allowed_name + "/"

        if normalized.startswith(
            prefix
        ):

            normalized = normalized[
                len(prefix):
            ]

        return os.path.realpath(
            os.path.join(
                base,
                normalized
            )
        )



    def validate_path(
        self,
        path
    ):


        base = os.path.realpath(

            self.ALLOWED_DIR

        )


        target = self.resolve_target(

            path,

            base

        )



        # startswith() is not a path boundary:
        #
        #     base   = /srv/bcos/data
        #     target = /srv/bcos/data_secret/key.txt
        #
        # would pass a prefix test while living outside the
        # allowed directory. Compare path components instead.

        if (
            target != base
            and not target.startswith(
                base + os.sep
            )
        ):

            raise PermissionError(

                "File outside allowed directory"

            )



        if not os.path.exists(

            target

        ):

            # Report the path the caller asked for, not the
            # resolved one: the absolute form leaked the host
            # filesystem layout into the answer and into the
            # evidence the model cites.

            raise FileNotFoundError(

                f"Không tìm thấy file: {path!r}"

            )


        if not os.path.isfile(

            target

        ):

            raise IsADirectoryError(

                f"Không phải file: {path!r}"

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