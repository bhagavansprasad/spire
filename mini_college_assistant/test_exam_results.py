
from tools import query_exam_results

results = query_exam_results()

for row in results:
    print(row)
