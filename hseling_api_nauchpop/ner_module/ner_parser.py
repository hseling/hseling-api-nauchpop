from .launch_tomita import launch_tomita
from .parse_tomita_xml import parse_user_text
import re


def extract_ner(user_text: str) -> list:
    '''Main function to call in web
    application'''

    code = launch_tomita(user_text)
    if code == 0:
        names = parse_user_text(user_text)
    else:
        names = ['tomita', 'doesnt work']

    # names = parse_user_text(user_text)
    if names:
        return ', '.join(names)
    else:
        return '            '


def markup_ner(user_text: str) -> None:
    '''Function annotates names in a text
    string with conventional tags. Optional
    for web application'''
    def tag_names(user_text: str, names: list):
        search_pattern = '|'.join(names)
        replace_pattern = r'<\&\g<0>!\&'
        return re.sub(search_pattern, replace_pattern, user_text)

    launch_tomita(user_text)
    names = parse_user_text(user_text)
    return tag_names(user_text, names)
