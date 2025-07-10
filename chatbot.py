import os
import re
import json

from flask import Flask
from flask import jsonify
from flask import request
from openai import OpenAI
from dotenv import load_dotenv


load_dotenv()


GPT_4O_MODEL = os.getenv('GPT_4O_MODEL')
GPT_KEY = os.getenv('GPT_KEY')

application = Flask(__name__)
application.config['CORS_HEADERS'] = 'Content-Type'
application.config['CORS_RESOURCES'] = {r'/api/*': {'origins': '*'}}
application.config['PROPAGATE_EXCEPTIONS'] = True

client = OpenAI(api_key=GPT_KEY)


def get_response(user_messages):
    system_instruction = (
        "You are a helpful assistant. First answer the user's question, "
        'then generate three follow-up questions that are closely related to the topic. '
        'Finally, return **only** a strictly valid JSON object in the form:\n'
        '{"response": "<your answer>", "questions": ["...", "...", "..."]}'
    )
    messages = [m.copy() for m in user_messages]
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get('role') == 'user':
            messages[i]['content'].append({'type': 'text', 'text': system_instruction})
            break
    print(f'[get_response] {messages}')
    response = client.chat.completions.create(
        model=GPT_4O_MODEL,
        messages=messages,
        temperature=0
    )
    return response.choices[0].message.content


def extract_json(text):
    try:
        json_data = json.loads(text)
        if json_data != {}:
            return json_data
    except (Exception,):
        pass
    json_match = re.search(r"```(?:json)?(.+?)```", text, re.DOTALL)
    if json_match:
        json_content = json_match.group(1).strip()
        try:
            json_data = json.loads(json_content)
            if json_data != {}:
                return json_data
        except (Exception,):
            pass
    dict_match = re.search(r"(\{.*\})", text, re.DOTALL)
    if dict_match:
        dict_content = dict_match.group(1).strip()
        try:
            dict_data = eval(dict_content)
            if isinstance(dict_data, dict) and dict_data != {}:
                return dict_data
        except (Exception,):
            pass
    return {}


@application.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json(silent=True) or {}
    try:
        response = get_response(data)
        print('[chat] Raw response:', response)
        response_json = extract_json(response)
        print('[chat] JSON response:', response_json)
        return jsonify(response_json)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


if __name__ == '__main__':
    application.run(host='0.0.0.0', port=5050)
