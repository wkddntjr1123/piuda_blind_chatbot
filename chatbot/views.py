from rest_framework import viewsets
from config.settings import BASE_DIR
from .serializers import WelfareSerializer
from .models import Classification, Welfare
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import requests
from bs4 import BeautifulSoup as bs
from google.cloud import dialogflow
import json, os
from time import sleep
from proto import Message
from django.forms.models import model_to_dict

# viewset으로 CRUD 자동 구현
class WelfareViewSet(viewsets.ModelViewSet):
    queryset = Welfare.objects.all()
    serializer_class = WelfareSerializer


# beautifulsoup 테스트
def beautifulsoupTest(request):
    # requirement : requests 패키지 (기본 내장인 urllib보다 깔끔한 듯), beautifulsoap4 패키지
    url = "https://tcrosa.ichaward.org/gunsan/"

    response = requests.get(url)

    if response.status_code == 200:
        html = response.text
        soup = bs(html, "html.parser")
    else:
        print(response.status_code)

    crollingData = soup.select(".subject")

    return JsonResponse({"crolling data": crollingData})


# 보건복지부 보건복지상담센터 : FAQ 크롤링
def crolling123GoKr(request):
    # 보건의료
    URL1 = "http://129.go.kr/faq/faq01.jsp"
    # 사회복지
    URL2 = "http://129.go.kr/faq/faq02.jsp"
    # 인구아동
    URL3 = "http://129.go.kr/faq/faq03.jsp"
    # 위기대응
    URL4 = "http://129.go.kr/faq/faq04.jsp"
    # 노인장애인
    URL5 = "http://129.go.kr/faq/faq05.jsp"
    page = int(1)
    queryParam = f"?page={page}&menu=1&tid=1&kind=0&table_id2=ZZZ"

    response = requests.get(URL1 + queryParam)
    if response.status_code == 200:
        html = response.text
        soup = bs(html, "html.parser")
    else:
        print(response.status_code)

    crollingData = soup.select(".subject>a")
    for item in crollingData:
        print(item["href"])
    # crollingData = soup.select_one(".grade-modal > div > .modal-content").text

    return JsonResponse({"crolling data": "123"})


def detect_intent_texts(project_id, location_id, session_id, text, language_code):
    # 동일한 세션ID로 통신을 하면 지속적인 대화가 가능하다. (약 20분 유지)
    session_client = dialogflow.SessionsClient(
        client_options={"api_endpoint": f"{location_id}-dialogflow.googleapis.com"}
    )
    session = f"projects/{project_id}/locations/{location_id}/agent/sessions/{session_id}"

    text_input = dialogflow.TextInput(text=text, language_code=language_code)
    query_input = dialogflow.QueryInput(text=text_input)

    response = session_client.detect_intent(
        request={"session": session, "query_input": query_input}
    )
    # dialogflow의 결과를 dict로 변환
    dict_response = Message.to_dict(response)
    fulfillment_text = dict_response.get("query_result").get("fulfillment_text")

    query_response = None
    responseData = None
    # "추천해드리는 복지 정보는 다음과 같습니다" => 결과오브젝트 함께 리턴
    if "추천" in fulfillment_text and "정보" in fulfillment_text:
        params = dict_response.get("query_result").get("output_contexts")[0].get("parameters")
        ageValue = params.get("age")[0]
        area = params.get("area")[0]
        interest = params.get("interest")[0]

        URL = "https://www.bokjiro.go.kr/ssis-teu/TWAT52005M/twataa/wlfareInfo/selectWlfareInfo.do"
        headers = {
            "Host": "www.bokjiro.go.kr",
            "Content-Type": "application/json; charset=UTF-8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36",
        }
        requestBody = {
            "dmSearchParam": {
                "page": "1",
                "onlineYn": "",
                "searchTerm": "",
                "tabId": "1",
                "orderBy": "date",
                "bkjrLftmCycCd": "",
                "daesang": "",
                "period": "",
                "age": ageValue,
                "region": area,
                "jjim": "",
                "subject": "",
                "favoriteKeyword": "Y",
                "sido": "",
                "gungu": "",
                "endYn": "",
            },
            "menuParam": {
                "mnuId": "",
                "pgmId": "",
                "wlfareInfoId": "",
                "scrnCmpntId": "",
                "curScrId": "",
            },
            "dmScr": {"curScrId": "teu/app/twat/twata/twataa/TWAT52005M"},
        }
        interestDomain = [
            "신체건강",
            "정신건강",
            "생활지원",
            "주거",
            "일자리",
            "문화·여가",
            "안전·위기",
            "임신·출산",
            "보육",
            "교육",
            "임신·위탁",
            "보호·돌봄",
            "서민금융",
            "법률",
        ]
        # 사용자가 말한 관심주제가 관심주제에 있으면, 관심주제로
        if interest in interestDomain:
            requestBody["dmSearchParam"]["subject"] = interest
        # 사용자가 말한 관심주제가 관심주제에 없으면, 키워드로
        else:
            requestBody["dmSearchParam"]["searchTerm"] = interest

        responseData = json.loads(
            requests.post(URL, headers=headers, data=json.dumps(requestBody)).text
        )
        # 중앙부처 데이터
        centralData = responseData.get("dsServiceList1")
        # 지자체 데이터
        localData = responseData.get("dsServiceList2")

        # 중앙부처 데이터가 존재하면 중앙부처 데이터 리턴
        if len(centralData):
            return fulfillment_text, centralData[0]
        # 중앙부처 데이터 없으면 지자체 데이터 리턴
        else:
            return fulfillment_text, localData[0]
    return fulfillment_text, responseData


# 환경변수 GOOGLE_APPLICATION_CREDENTIALS 등록하면 Google Cloud SDK가 알아서 사용자 계정으로 인증처리
# input : {"texts":"내용", "sessionId":"세션ID"}
# output : {"input texts":"입력내용", "result texts":"결과내용", "sessionId":"세션ID", "resultData":{최종결과오브젝트})
@csrf_exempt
def dialogflowTest(request):

    SESSION_ID = json.loads(request.body)["sessionId"]
    inputText = json.loads(request.body)["texts"]

    credentials = os.path.join(BASE_DIR, "credentials.json")
    # GOOGLE_APPLICATION_CREDENTIALS 환경변수 등록
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials

    PROJECT_ID = "welfare-chat-gm9e"
    LANGUAGE_CODE = "ko"
    LOCATION_ID = "asia-northeast1"

    resultTexts, resultData = detect_intent_texts(
        PROJECT_ID, LOCATION_ID, SESSION_ID, inputText, LANGUAGE_CODE
    )
    response = {"input texts": inputText, "result texts": resultTexts, "sessionId": SESSION_ID}
    # 최종적으로 반환되는 결과 오브젝트가 존재하면 함께 반환
    if resultData is not None:
        response.update({"resultData": resultData})

    return JsonResponse(response)


# 전체 DB 생성 함수
def createAllWelfareData(request):
    # DB classification 생성
    try:
        if Classification.objects.get(name="central"):
            pass
    except Exception as e:
        newClassification = Classification()
        newClassification.name = "central"
        newClassification.save()

    try:
        if Classification.objects.get(name="local"):
            pass
    except Exception as e:
        newClassification = Classification()
        newClassification.name = "local"
        newClassification.save()
    # Request
    URL = "https://www.bokjiro.go.kr/ssis-teu/TWAT52005M/twataa/wlfareInfo/selectWlfareInfo.do"
    body = {
        "dmSearchParam": {
            "page": "1",
            "onlineYn": "",
            "searchTerm": "",
            "tabId": "1",
            "orderBy": "date",
            "bkjrLftmCycCd": "",
            "daesang": "",
            "period": "",
            "age": "",
            "region": "",
            "jjim": "",
            "subject": "",
            "favoriteKeyword": "Y",
            "sido": "",
            "gungu": "",
        },
        "menuParam": {
            "mnuId": "",
            "pgmId": "",
            "wlfareInfoId": "",
            "scrnCmpntId": "",
            "curScrId": "",
        },
        "dmScr": {"curScrId": "teu/app/twat/twata/twataa/TWAT52005M"},
    }
    headers = {
        "Host": "www.bokjiro.go.kr",
        "Content-Type": "application/json; charset=UTF-8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36",
    }
    responseData = json.loads(requests.post(URL, headers=headers, data=json.dumps(body)).text)

    i = 1
    while True:
        body["dmSearchParam"]["page"] = i
        responseData = json.loads(requests.post(URL, headers=headers, data=json.dumps(body)).text)

        # 중앙부처 데이터
        centralData = responseData["dsServiceList1"]
        # 지자체 데이터
        localData = responseData["dsServiceList2"]

        # 탈출 조건 : 지자체 데이터 개수 0
        if len(localData) == 0:
            break

        # 중앙부처 데이터 DB화
        for item in centralData:
            id = item.get("WLFARE_INFO_ID", "")
            title = item.get("WLFARE_INFO_NM", "").replace(",", "/")
            content = item.get("WLFARE_INFO_OUTL_CN", "")
            address = item.get("ADDR", "")
            if address == " ":
                address = ""
            phone = item.get("RPRS_CTADR", "")
            department = item.get("BIZ_CHR_INST_NM", "")

            # family, lifecycle, age
            complexData = item.get("RETURN_STR")
            complexList = complexData.split(";")
            complexDict = {}
            for listItem in complexList:
                complexDict.update({listItem.split(":")[0]: listItem.split(":")[1]})
            interest = complexDict.get("INTRS_THEMA_CD", "").replace(",", "/")
            family = complexDict.get("FMLY_CIRC_CD", "").replace(",", "/")
            lifecycle = complexDict.get("BKJR_LFTM_CYC_CD", "").replace(",", "/")
            ageText = complexDict.get("WLFARE_INFO_AGGRP_CD", "")
            age = ""
            if "0~5" in ageText:
                age += "0"
            if "6~12" in ageText:
                age += "1"
            if "13~18" in ageText:
                age += "2"
            if "19~39" in ageText:
                age += "3"
            if "40~64" in ageText:
                age += "4"
            if "65" in ageText:
                age += "5"
            classification = Classification.objects.get(name="central")
            dto = {
                "id": id,
                "title": title,
                "content": content,
                "interest": interest,
                "family": family,
                "lifecycle": lifecycle,
                "age": age,
                "address": address,
                "phone": phone,
                "department": department,
                "classification": classification,
            }
            Welfare.objects.create(**dto)
        # 지자체 데이터 DB화
        for item in localData:
            id = item.get("WLFARE_INFO_ID", "")
            title = item.get("WLFARE_INFO_NM", "").replace(",", "/")
            content = item.get("WLFARE_INFO_OUTL_CN", "")
            address = item.get("ADDR", "")
            if address == " ":
                address = ""
            phone = item.get("RPRS_CTADR", "")
            department = item.get("BIZ_CHR_INST_NM", "")

            # family, lifecycle, age
            complexData = item.get("RETURN_STR")
            complexList = complexData.split(";")
            complexDict = {}
            for listItem in complexList:
                complexDict.update({listItem.split(":")[0]: listItem.split(":")[1]})
            interest = complexDict.get("INTRS_THEMA_CD", "").replace(",", "/")
            family = complexDict.get("FMLY_CIRC_CD", "").replace(",", "/")
            lifecycle = complexDict.get("BKJR_LFTM_CYC_CD", "").replace(",", "/")
            ageText = complexDict.get("WLFARE_INFO_AGGRP_CD", "")
            age = ""
            if "0~5" in ageText:
                age += "0"
            if "6~12" in ageText:
                age += "1"
            if "13~18" in ageText:
                age += "2"
            if "19~39" in ageText:
                age += "3"
            if "40~64" in ageText:
                age += "4"
            if "65" in ageText:
                age += "5"
            classification = Classification.objects.get(name="local")
            dto = {
                "id": id,
                "title": title,
                "content": content,
                "interest": interest,
                "family": family,
                "lifecycle": lifecycle,
                "age": age,
                "address": address,
                "phone": phone,
                "department": department,
                "classification": classification,
            }
            Welfare.objects.create(**dto)
        i = i + 1
        sleep(1)
    return JsonResponse({"...": "ㅠㅠ"})
