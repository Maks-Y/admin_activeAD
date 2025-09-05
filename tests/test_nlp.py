from email.message import EmailMessage
from datetime import datetime

from ai.nlp import parse_hr_mail


def test_parse_hr_mail_valid():
    msg = EmailMessage()
    msg.set_content("Просьба уволить Иванов Иван Иванович 1 июля 2024")
    fio, date = parse_hr_mail(msg)
    assert fio == "Иванов Иван Иванович"
    assert isinstance(date, datetime)
    assert date.date() == datetime(2024, 7, 1).date()


def test_parse_hr_mail_invalid():
    msg = EmailMessage()
    msg.set_content("Неразборчивое письмо без нужных данных")
    fio, date = parse_hr_mail(msg)
    assert fio is None
    assert date is None
