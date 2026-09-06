from tools.search import SearchTool


search = SearchTool()


query = "who is the president of the United States in 2026"


print("=" * 60)
print("DuckDuckGo Search Test")
print("=" * 60)


result = search.run(query)


print(result)