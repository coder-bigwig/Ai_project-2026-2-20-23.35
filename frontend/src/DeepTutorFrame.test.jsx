import { getDeepTutorErrorMessage } from './DeepTutorFrame';

test('uses backend detail in DeepTutor SSO error message', () => {
    const err = {
        response: {
            data: {
                detail: 'DeepTutor SSO not configured (missing DEEPTUTOR_AUTH_SECRET or shared volume)'
            }
        }
    };

    expect(getDeepTutorErrorMessage(err)).toBe(
        'DeepTutor login failed: DeepTutor SSO not configured (missing DEEPTUTOR_AUTH_SECRET or shared volume)'
    );
});
