from flask import jsonify

def _get_code_message(code):

    match code:
        case 200:
            return "OK"
        case 201:
            return "Created"
        case 202:
            return "Accepted"
        case 203:
            return "Non-Authoritative Information"
        case 204:
            return "No Content"


        case 400:
            return "Bad Request"
        case 401:
            return "Unauthorized"
        case 403:
            return "Forbidden"
        case 404:
            return "Not Found"
        case 409:
            return "Conflict"


        case 500:
            return "Internal Server Error"
        case 501:
            return "Not Implemented"
        case 502:
            return "Bad Gateway"
        case 503:
            return "Service Unavailable"
        case 504:
            return "Gateway Timeout"
        case 509:
            return "Network Timeout"

        case _:
            return None

class RMessage:

    def __init__(self,response_code = 200):
        self.message = {"message" : _get_code_message(response_code)}
        self.code = response_code

            

    def get(self):
        return jsonify(self.message), self.code

    def add(self,key,value):
        self.message[key] = value
        return self

    def msg(self,value):
        return self.add("message",value)


class RErrorMessage(RMessage):

    def __init__(self, 
                 error_text = "Unexpected error", 
                 response_code = 501):

        super().__init__(response_code)

        self.message["error"] = error_text
        
