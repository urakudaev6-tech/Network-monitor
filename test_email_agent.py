import unittest
from unittest.mock import patch
import email_agent as agent

class AgentTests(unittest.TestCase):
    @patch.object(agent, 'api')
    def test_status(self, api):
        api.return_value = [{'id': 5, 'subnet': '192.168.100.0/24', 'detected': 127, 'total': 254}]
        body, attachment = agent.execute('NM STATUS')
        self.assertIn('127 / 254', body)
        self.assertIsNone(attachment)

    @patch.object(agent, 'api')
    def test_changes(self, api):
        def fake(path, params=None):
            if path == '/scanner/history':
                return [{'id': 5, 'subnet': 'a'}, {'id': 4, 'subnet': 'a'}]
            if path.endswith('/5'):
                return {'devices': [{'ip': '1.1.1.1', 'detected': True}]}
            return {'devices': [{'ip': '2.2.2.2', 'detected': True}]}
        api.side_effect = fake
        body, _ = agent.execute('NM CHANGES')
        self.assertIn('NEW: 1.1.1.1', body)
        self.assertIn('NO_RESPONSE: 2.2.2.2', body)

    def test_unknown_command(self):
        self.assertIsNone(agent.execute('STATUS'))
        self.assertIn('Unknown', agent.execute('NM BAD')[0])

    @patch.object(agent, 'api')
    def test_device_exact_match(self, api):
        api.return_value = [{'ip': '192.168.100.51'}, {'ip': '192.168.100.5', 'mac': 'AA'}]
        body, _ = agent.execute('NM DEVICE 192.168.100.5')
        self.assertIn('AA', body)
        self.assertNotIn('.51', body)

if __name__ == '__main__':
    unittest.main()
