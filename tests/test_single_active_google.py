from contextlib import contextmanager
from unittest.mock import MagicMock,patch
import pytest
from autogpt.coaching import identity_enrollment as ie
UID='11111111-1111-4111-8111-111111111111'
@pytest.mark.parametrize('flow',['confirm','recovery'])
def test_other_active_subject_rejected_without_consuming(flow):
 cur=MagicMock()
 grant={'user_id':UID,'subject':'new','source':'telegram_google_dual_proof','google_email':'new@example.com'}
 cur.fetchone.side_effect=[grant,{'account_status':'active'},{'subject':'existing'}]
 @contextmanager
 def db(**kw):
  assert kw=={'commit':True}
  yield cur
 with patch.object(ie,'get_db_cursor',db):
  with pytest.raises(ie.EnrollmentConflict,match='active Google'):
   ie.confirm_google('t','b') if flow=='confirm' else ie.complete_recovery('t','b','new','new@example.com')
 statements=[x.args[0] for x in cur.execute.call_args_list]
 assert not any('INSERT INTO' in x or 'SET consumed_at' in x for x in statements)
 assert next(i for i,x in enumerate(statements) if 'user_profiles' in x)<next(i for i,x in enumerate(statements) if 'subject<>' in x)
 assert not any('UPDATE user_profiles' in x or 'SET revoked_at' in x for x in statements)

def test_recovery_uses_fresh_second_google_proof_email_only():
 cur=MagicMock();cur.fetchone.side_effect=[{'user_id':UID},{'account_status':'active'},None,None]
 @contextmanager
 def db(**kw):yield cur
 with patch.object(ie,'get_db_cursor',db):assert ie.complete_recovery('t','b','s','fresh@example.com')==UID
 insert=next(x for x in cur.execute.call_args_list if 'INSERT INTO google_login_credentials' in x.args[0])
 assert insert.args[1]==('s',UID,'fresh@example.com')
 assert not any('UPDATE user_profiles' in x.args[0] for x in cur.execute.call_args_list)

@pytest.mark.parametrize('email',[None,'',42,' '*3,'a'*255])
def test_missing_or_invalid_recovery_email_has_no_db_access(email):
 with patch.object(ie,'get_db_cursor') as db:
  with pytest.raises(ie.EnrollmentConflict):ie.complete_recovery('t','b','s',email)
 db.assert_not_called()
