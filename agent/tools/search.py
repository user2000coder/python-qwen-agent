"""
BCOS Search Tool
DuckDuckGo DDGS
"""

from ddgs import DDGS

from config import SEARCH_RESULTS



class SearchTool:



    name = "search"



    def __init__(self):

        self.client = DDGS()



    # =====================================================
    # Run Search
    # =====================================================

    def run(
        self,
        query
    ):


        try:


            results = []


            data = self.client.text(

                query,

                max_results=
                SEARCH_RESULTS

            )



            for item in data:


                results.append({

                    "title":
                        item.get(
                            "title",
                            ""
                        ),


                    "url":
                        item.get(
                            "href",
                            ""
                        ),


                    "content":
                        item.get(
                            "body",
                            ""
                        )

                })



            return {


                "success":
                    True,


                "query":
                    query,


                "count":
                    len(results),


                "results":
                    results


            }



        except Exception as e:



            return {


                "success":
                    False,


                "query":
                    query,


                "error":
                    str(e),


                "results":
                    []

            }