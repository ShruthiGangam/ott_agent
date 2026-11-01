"""Test-only scripted responses. Application code cannot select this provider."""
from unittest.mock import patch
from ott_agent.provider import Provider
class ScriptedProvider(Provider):
    def __init__(self, timeout=.01):
        with patch.object(Provider,'validate_environment',return_value=('https://unit.test/api','test-only','test-only')):
            super().__init__(timeout=timeout)
    def choose(self, goal_ids, plays, completions, fault=None, unavailable=False):
        if fault or unavailable:
            return super().choose(goal_ids,plays,completions,fault,unavailable)
        return {'goal_id':goal_ids[0],'confidence':.6}
    def plan(self,context,fault=None,unavailable=False):
        if fault or unavailable:
            return super().plan(context,fault,unavailable)
        proposal=self.choose([g['goal_id'] for g in context['eligible_goals']],context['activity']['plays'],context['activity']['completions'])
        return dict(proposal,intervention='home_page',reason_code='next_step',evidence_keys=[context['evidence'][0]['key']])
