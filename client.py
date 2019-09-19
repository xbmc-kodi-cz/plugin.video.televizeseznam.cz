import urllib2
import json

class GraphQLClient:
    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.token = None
        self.headername = None

    def execute(self, query, variables=None):
        return self._send(query, variables)

    def inject_token(self, token, headername='Authorization'):
        self.token = token
        self.headername = headername

    def _send(self, query, variables):
	
        data = {'query': query,
                'variables': json.dumps(variables)}
        headers = {'Accept': 'application/json',
                   'Content-Type': 'application/json'}

        if self.token is not None:
            headers[self.headername] = '{}'.format(self.token)

        req = urllib2.Request(self.endpoint, json.dumps(data).encode('utf-8'), headers)

        try:
            response = urllib2.urlopen(req)
            return json.loads(response.read().decode('utf-8'))
        except urllib2.HTTPError as e:
            print((e.read()))
            print('')
            raise e
