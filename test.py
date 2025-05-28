import requests


def send_pushover_notification(title=None):
    data = {
        "token": "ahgmdyoronmocd9u7gv8a3kfgnn1vj",
        "user": "un1w1m9y38e18kr5pmaj45gyakpat9",
        "message": "hello",
    }
    if title:
        data["title"] = title

    response = requests.post(
        "https://api.pushover.net/1/messages.json", data=data)
    return response


if __name__ == "__main__":
    response = send_pushover_notification("Test Notification")
    print(response.status_code)
    print(response.text)
    if response.status_code == 200:
        print("Notification sent successfully!")
    else:
        print("Failed to send notification.")
