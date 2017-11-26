from tprofile import Profiler
import requests

from tprofile.bokeh import serve

def test_basic():
    with Profiler(serve=True, port=5006) as prof:
        response = requests.get('http://localhost:5006/main')
        assert response.status_code == 200
