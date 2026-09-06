"""
BCOS Evidence Evaluation Agent
"""


class EvidenceAgent:


    role = "Evidence Evaluator"



    def prompt(
        self,
        question,
        evidence
    ):


        return f"""

Bạn là Evidence Evaluator trong hệ thống BCOS.



CÂU HỎI:

{question}



EVIDENCE:

{evidence}



NHIỆM VỤ:

Đánh giá chất lượng bằng chứng.



Phân tích:



1. SOURCE QUALITY

Nguồn có đáng tin không?

Ví dụ:

- Nguồn chính thức
- Báo chí uy tín
- Wiki
- Nguồn không xác định



2. RELEVANCE

Evidence có thực sự trả lời câu hỏi không?



3. FRESHNESS

Thông tin có phù hợp với thời điểm câu hỏi không?



4. COMPLETENESS

Có đủ dữ liệu để kết luận không?



5. CONFIDENCE

Đánh giá:

Cao
Trung bình
Thấp



Trả lời theo mẫu:


SOURCE QUALITY:
...


RELEVANCE:
...


FRESHNESS:
...


COMPLETENESS:
...


CONFIDENCE:
...


RECOMMENDATION:
...

"""