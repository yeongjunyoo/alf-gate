#!/usr/bin/env python3
"""SYNTHETIC data generator for the alf-gate demo.

Writes data/ files with real-world column names:
- cafe24_products.csv   (cafe24 상품 엑셀 실제 열 이름 부분집합)
- channeltalk_userchats.csv / channeltalk_messages.csv (채널톡 상담 다운로드 시트 열 이름)
- knowledge_articles.json (ALF 지식 설정에 해당하는 아티클, 함정 1개 포함)
- policies.json (정책 원장: 결정론 채점의 사실 기준)

All content is SYNTHETIC and deterministic (seeded).
"""
import csv
import json
import os
import random

random.seed(718)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- products
PRODUCTS = [
    # 코드, 상품명, 판매가, 요약, 옵션, 배송기간, 비고정책
    ("GB-001", "스탠다드 에코백", 15900, "데일리 코튼 에코백, 350g 캔버스", "색상{크림/차콜/올리브}", "1~2일", ""),
    ("GB-002", "라지 에코백", 19900, "노트북 수납 가능한 대용량", "색상{크림/블랙}", "1~2일", ""),
    ("GB-003", "크로스 에코백", 22000, "스트랩 길이 조절 크로스백", "색상{베이지/네이비}", "1~2일", "품절"),
    ("GB-004", "코튼 파우치", 8900, "속주머니용 미니 파우치", "색상{크림/차콜}", "1~2일", ""),
    ("GB-005", "자수 커스텀 에코백", 24900, "이니셜 자수 주문제작", "자수{영문 이니셜 3자}", "제작 5일", "주문제작"),
    ("GB-006", "텀블러백", 12900, "보냉 안감 텀블러 전용", "색상{크림/올리브}", "1~2일", ""),
    ("GB-007", "리필 스트랩", 4900, "교체용 어깨 스트랩", "색상{블랙/베이지}", "1~2일", ""),
    ("GB-008", "기프트 세트", 39900, "에코백과 파우치 선물 구성", "색상{크림/차콜}", "1~2일", ""),
]

RETURN_GUIDE = "단순변심 반품은 수령 후 7일 이내 접수. 편도 배송비 3,000원 고객 부담. 마이페이지 주문내역에서 접수"
RETURN_GUIDE_CUSTOM = "주문제작 상품은 제작 착수 후 취소와 반품 불가. 불량은 수령 후 7일 이내 무상 교환"
SHIPPING_GUIDE = "평일 오후 2시 이전 결제 건 당일 출고. 30,000원 이상 무료배송, 미만 3,000원. 제주와 도서산간 3,000원 추가"

with open(os.path.join(OUT, "cafe24_products.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["상품 코드", "자체 상품 코드", "진열 상태", "판매 상태", "상품명", "상품 요약 설명",
                "판매가", "옵션입력", "배송 방법", "배송기간", "배송비 구분", "배송비 입력",
                "상품 배송 안내", "교환/반품 안내"])
    for code, name, price, desc, opt, days, note in PRODUCTS:
        sale = "품절" if note == "품절" else "판매함"
        ret = RETURN_GUIDE_CUSTOM if note == "주문제작" else RETURN_GUIDE
        w.writerow([code, f"SELF-{code}", "진열함", sale, name, desc, price, opt,
                    "택배", days, "조건부 무료", "3000", SHIPPING_GUIDE, ret])

# ---------------------------------------------------------------- knowledge
ARTICLES = [
    {"id": "KA-01", "title": "배송 안내",
     "body": "평일 오후 2시 이전 결제하신 주문은 당일 출고됩니다. 출고 후 1~2일 내 도착합니다. 30,000원 이상 구매 시 무료배송이며 미만은 배송비 3,000원입니다. 제주와 도서산간 지역은 3,000원이 추가됩니다."},
    {"id": "KA-02", "title": "반품 안내",
     "body": "단순변심 반품은 상품 수령 후 7일 이내에 접수하실 수 있습니다. 마이페이지 주문내역에서 반품 신청 버튼으로 접수해 주세요. 상품 불량은 배송비 없이 처리됩니다."},
    {"id": "KA-03", "title": "반품 배송비 이벤트 안내",
     "body": "지금은 무료 반품 이벤트 기간입니다. 단순변심 반품도 배송비는 저희가 부담하니 부담 없이 반품하세요. 마이페이지에서 접수해 주세요."},
    {"id": "KA-04", "title": "교환 안내",
     "body": "동일 상품의 옵션 교환만 가능합니다. 교환 배송비는 왕복 6,000원이며 고객님 부담입니다. 다른 상품으로 변경은 반품 후 재주문을 이용해 주세요."},
    {"id": "KA-05", "title": "쿠폰 안내",
     "body": "첫 구매 쿠폰은 10% 할인이며 30,000원 이상 주문에만 적용됩니다. 다른 쿠폰과 중복 사용은 불가합니다. 유효기간은 발급일로부터 30일입니다."},
    {"id": "KA-06", "title": "재입고 안내",
     "body": "품절 상품은 상품 페이지의 재입고 알림을 신청해 주세요. 재입고 일정은 확정 전에는 안내하지 않는 것이 원칙입니다."},
    {"id": "KA-07", "title": "주문제작 상품 안내",
     "body": "자수 커스텀 에코백은 결제 후 제작에 5일이 걸립니다. 제작 착수 후에는 취소와 반품이 불가합니다. 이니셜 오탈자는 주문 당일 자정까지만 수정할 수 있습니다."},
    {"id": "KA-08", "title": "세탁과 관리 안내",
     "body": "면 소재 제품은 찬물에 단독 손세탁을 권장합니다. 표백제 사용과 건조기 사용은 피해 주세요. 자수 제품은 뒤집어서 세탁해 주세요."},
    {"id": "KA-09", "title": "배송지 변경 안내",
     "body": "배송지 변경은 송장 출력 전까지만 가능합니다. 주문 후 채널톡으로 주문번호와 함께 요청해 주세요. 송장 출력 후에는 택배사 반송 절차를 안내해 드립니다."},
]
json.dump(ARTICLES, open(os.path.join(OUT, "knowledge_articles.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

# ---------------------------------------------------------------- policies
POLICIES = [
    {"topic": "return_fee", "keywords": ["반품", "배송비"], "fact": "단순변심 반품 배송비는 편도 3,000원 고객 부담",
     "source": "cafe24_products.csv > 교환/반품 안내"},
    {"topic": "return_window", "keywords": ["반품", "7일", "기한"], "fact": "단순변심 반품은 수령 후 7일 이내",
     "source": "cafe24_products.csv > 교환/반품 안내"},
    {"topic": "free_shipping", "keywords": ["무료배송", "배송비"], "fact": "30,000원 이상 무료배송, 미만 3,000원",
     "source": "cafe24_products.csv > 상품 배송 안내"},
    {"topic": "shipping_cutoff", "keywords": ["당일 출고", "출고", "오후 2시"], "fact": "평일 오후 2시 이전 결제 건만 당일 출고",
     "source": "cafe24_products.csv > 상품 배송 안내"},
    {"topic": "coupon_first", "keywords": ["첫 구매", "쿠폰", "10%"], "fact": "첫 구매 쿠폰은 10% 할인, 30,000원 이상 주문만, 중복 불가",
     "source": "knowledge_articles.json > 쿠폰 안내"},
    {"topic": "restock", "keywords": ["재입고", "입고"], "fact": "재입고 일정은 확정 전 안내 금지",
     "source": "knowledge_articles.json > 재입고 안내"},
    {"topic": "custom_no_return", "keywords": ["주문제작", "자수", "반품"], "fact": "주문제작 상품은 제작 착수 후 취소와 반품 불가",
     "source": "cafe24_products.csv > GB-005 교환/반품 안내"},
    {"topic": "exchange_fee", "keywords": ["교환", "배송비"], "fact": "옵션 교환 배송비는 왕복 6,000원 고객 부담",
     "source": "knowledge_articles.json > 교환 안내"},
    {"topic": "address_change", "keywords": ["배송지", "변경"], "fact": "배송지 변경은 송장 출력 전까지만 가능",
     "source": "knowledge_articles.json > 배송지 변경 안내"},
]
json.dump(POLICIES, open(os.path.join(OUT, "policies.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

# ---------------------------------------------------------------- chats
# 클러스터 분포: 배송 34, 반품 28, 재고 18, 쿠폰 14, 상품정보 10, 해외 9, B2B 7 = 120
Q = {
    "배송": [
        ("어제 주문했는데 언제 출고되나요?", "평일 오후 2시 이전 결제 건은 당일 출고됩니다. 어제 오후 결제셔서 오늘 출고 예정입니다."),
        ("배송비가 왜 붙었나요? 무료 아닌가요?", "30,000원 이상 구매 시 무료배송입니다. 이번 주문은 {price}원이라 배송비 3,000원이 부과됐습니다."),
        ("제주도인데 배송되나요?", "제주 지역은 배송 가능합니다. 도서산간 추가 배송비 3,000원이 부과됩니다."),
        ("오늘 시키면 내일 받을 수 있나요?", "오후 2시 이전 결제하시면 당일 출고되고 보통 출고 후 1~2일 내 도착합니다."),
        ("송장번호가 안 떠요", "출고 당일 저녁에 송장이 등록됩니다. 등록되면 알림톡으로 보내드립니다."),
        ("배송지를 잘못 입력했어요", "송장 출력 전이라 변경 가능합니다. 주문번호와 새 주소를 남겨 주세요."),
    ],
    "반품": [
        ("색이 화면과 달라서 반품하고 싶어요", "수령 후 7일 이내라 접수 가능합니다. 단순변심 반품은 편도 배송비 3,000원이 부과됩니다. 마이페이지에서 접수해 주세요."),
        ("반품 배송비 얼마예요?", "단순변심 반품은 편도 3,000원 고객 부담입니다. 불량이면 저희가 부담합니다."),
        ("받은 지 열흘 됐는데 반품 되나요?", "단순변심 반품 기한은 수령 후 7일까지라 기한이 지났습니다. 양해 부탁드립니다."),
        ("자수 에코백 주문 취소하고 싶어요", "주문제작 상품은 제작 착수 후 취소가 불가합니다. 착수 전이면 바로 취소해 드릴게요. 주문번호 알려 주세요."),
        ("불량인 것 같아요. 박음질이 터져 있어요", "불편을 드려 죄송합니다. 불량 건은 배송비 없이 교환이나 반품 처리해 드립니다. 사진과 주문번호를 남겨 주세요."),
        ("교환하면 배송비 또 내야 하나요?", "옵션 교환은 왕복 6,000원이 부과됩니다. 반품 후 재주문이 더 유리할 수 있어요."),
    ],
    "재고": [
        ("크로스 에코백 재입고 언제 되나요?", "재입고 일정은 아직 확정되지 않았습니다. 상품 페이지에서 재입고 알림을 신청해 주세요."),
        ("네이비 색상 품절인데 다시 나오나요?", "확정된 일정은 안내드리기 어렵습니다. 재입고 알림을 신청해 주시면 가장 빠르게 받아보실 수 있어요."),
        ("올리브 색 재고 있나요?", "네, 현재 구매 가능합니다."),
    ],
    "쿠폰": [
        ("첫구매 쿠폰이 적용이 안 돼요", "첫 구매 쿠폰은 30,000원 이상 주문에만 적용됩니다. 현재 장바구니 금액을 확인해 주세요."),
        ("쿠폰 두 개 같이 쓸 수 있나요?", "쿠폰 중복 사용은 불가합니다. 할인율이 높은 쿠폰 하나만 적용해 주세요."),
        ("쿠폰 유효기간 지났는데 다시 주실 수 있나요?", "유효기간이 지난 쿠폰은 재발급이 어렵습니다. 진행 중인 다른 혜택을 확인해 주세요."),
    ],
    "상품정보": [
        ("에코백 세탁 어떻게 하나요?", "찬물에 단독 손세탁을 권장합니다. 건조기는 피해 주세요."),
        ("라지 에코백에 노트북 들어가나요?", "네, 15인치 노트북까지 수납 가능합니다."),
        ("자수는 몇 글자까지 되나요?", "영문 이니셜 3자까지 가능합니다."),
    ],
    "해외": [
        ("미국으로 배송되나요?", "현재 해외 배송 정책을 확인해서 다시 안내드리겠습니다."),
        ("일본 배송 관세 어떻게 되나요?", "담당자 확인 후 안내드리겠습니다."),
    ],
    "B2B": [
        ("100개 단체 주문 견적 받고 싶어요", "대량 주문은 담당자가 별도로 견적을 안내드립니다. 연락처를 남겨 주세요."),
        ("기업 로고 인쇄 가능한가요?", "수량과 일정에 따라 달라서 담당자 확인 후 회신드리겠습니다."),
    ],
}
DIST = [("배송", 34), ("반품", 28), ("재고", 18), ("쿠폰", 14), ("상품정보", 10), ("해외", 9), ("B2B", 7)]
FOLLOWUP = {
    "배송": [("빠른 확인 감사합니다", None), ("네 알겠습니다", None)],
    "반품": [("접수했어요. 확인 부탁드려요", "접수 확인했습니다. 회수 기사님이 1~2일 내 방문합니다."), ("네 감사합니다", None)],
    "재고": [("알림 신청했어요", None)],
    "쿠폰": [("아 그렇군요", None)],
    "상품정보": [("감사합니다", None)],
    "해외": [("네 기다릴게요", None)],
    "B2B": [("메일로 보냈습니다", None)],
}
NAMES = ["김하윤", "박서준", "이지우", "최민서", "정도윤", "강서연", "조은우", "윤지호", "임수아", "한예준",
         "오시우", "신하은", "권주원", "황라온", "안다인", "송지안", "홍은호", "유채원", "문선우", "배가은"]

BASE = 1747500000000  # 2026-04-18경 (ms)
DAY = 86400000

uc_rows, msg_rows = [], []
chat_no = 0
for cluster, count in DIST:
    variants = Q[cluster]
    for i in range(count):
        chat_no += 1
        cid = f"UC-2026-{chat_no:04d}"
        q, a = variants[i % len(variants)]
        price = random.choice([12900, 15900, 19900, 24800, 27800])
        a = a.replace("{price}", f"{price:,}")
        t0 = BASE + random.randint(0, 90) * DAY + random.randint(32400000, 64800000)
        name = random.choice(NAMES)
        # 반품 클러스터에 일회성 배려 2건 심기: 정책과 다른 개별 판단 (정책 아님의 증거)
        if cluster == "반품" and i in (11, 19):
            a = "이번 건은 저희가 배송비를 부담해서 처리해 드릴게요. 다음 구매 시에는 반품 배송비 3,000원이 부과되는 점 양해 부탁드립니다."
        msgs = [("user", q, t0), ("manager", a, t0 + random.randint(120000, 1800000))]
        fu = random.choice(FOLLOWUP[cluster])
        if random.random() < 0.6:
            msgs.append(("user", fu[0], t0 + 2400000))
            if fu[1]:
                msgs.append(("manager", fu[1], t0 + 3000000))
        closed = msgs[-1][2] + 600000
        uc_rows.append([cid, name, q[:30], cluster, "closed", "appChat",
                        t0, t0, closed, random.choice([5, 5, 4, 5, 4, 3])])
        for j, (ptype, text, ts) in enumerate(msgs):
            msg_rows.append([cid, ptype, f"{'U' if ptype == 'user' else 'M'}-{chat_no:04d}", ts, text, "False"])

random.shuffle(uc_rows)
with open(os.path.join(OUT, "channeltalk_userchats.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["id", "name", "title", "tags", "state", "mediumType", "createdAt", "firstAskedAt", "closedAt", "profile.csat"])
    w.writerows(uc_rows)
with open(os.path.join(OUT, "channeltalk_messages.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["ChatId", "PersonType", "PersonId", "CreatedAt", "PlainText", "isPrivate"])
    w.writerows(msg_rows)

readme = "# SYNTHETIC 데이터\n\n모든 파일은 데모용 합성 데이터다. 실제 고객 정보가 아니다.\n열 이름은 카페24 상품 엑셀과 채널톡 상담 다운로드 시트의 공개 문서 기준 실명을 따랐다.\n"
open(os.path.join(OUT, "README.md"), "w", encoding="utf-8").write(readme)
print(f"products={len(PRODUCTS)} articles={len(ARTICLES)} policies={len(POLICIES)} chats={len(uc_rows)} messages={len(msg_rows)}")
