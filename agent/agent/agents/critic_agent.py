"""
BCOS Critical Reviewer Agent
"""


class CriticAgent:


    role = "Critical Reviewer"



    def prompt(
        self,
        question,
        evidence
    ):


        return f"""

Bạn là Critical Reviewer của hệ thống BCOS.



CÂU HỎI:

{question}



EVIDENCE:

{evidence}



NHIỆM VỤ:

Tìm lỗi và rủi ro trong dữ liệu.



Kiểm tra:


1. CONTRADICTION

Có thông tin nào mâu thuẫn nhau không?


2. HALLUCINATION RISK

Có kết luận nào vượt quá Evidence không?


3. SOURCE QUALITY

Nguồn có đáng tin không?


4. MISSING INFORMATION

Còn thiếu dữ kiện quan trọng nào?



Trả lời:


PROBLEMS:
...


RISK LEVEL:
Cao / Trung bình / Thấp


RECOMMENDATION:
...


"""