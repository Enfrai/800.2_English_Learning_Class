# Public enquiry form (US-010 ST-04)

The standalone client component is not mounted on an application route yet.
US-009 can embed it below its public class/contact information:

```tsx
import PublicEnquiryForm from "@/components/enquiries/public-enquiry-form";

// Inside the public page's content:
<PublicEnquiryForm />
```

No props, Session provider or authentication are required. Scoped styles reuse
Ako UI Kit tokens with fallback values; existing pages and global styles are unchanged.
Each instance generates its own accessible label/error IDs.

The form posts JSON to `/api/user/enquiries`, without credentials or browser storage.
The server remains authoritative. Consent must be checked; message length counts
Unicode code points, matching Python. Overlong input is retained for correction,
shown with the exact AC4 error, and never submitted or silently truncated.
Successful submission clears the form. Failed requests preserve input and are not
automatically retried because a lost response may follow a successful database write.

Run the focused test with Node 20 or newer and Google Chrome available.
Install the locked development dependencies with npm (do not omit dev dependencies):

```sh
npm ci
node tests/public-enquiry-form.mjs
```

The runner creates a disposable Next.js app outside the repository, mounts the real
component, and mocks only the submission API in Chrome. It removes its own app and
processes afterward. No backend, database, Docker or existing application route is
used. These checks are not PostgreSQL or real-gateway integration evidence.

US-009 integration, a full accessibility audit, real API/gateway verification and
an agreed spam-protection policy remain separate work. Playwright 1.62.1 is pinned
in devDependencies and package-lock.json. Both tests use the installed Google Chrome
channel; npm ci does not install that browser. The tests do not install or replace Chrome.

## Coordinator list (ST-05)

The independent page is available at `/enquiries` under the existing staff layout.
The existing SessionShell supplies the authenticated UI identity. Middleware and
SessionShell restrict this route to Coordinators; the API independently validates
the current database role on every read. The Coordinator menu links to this page.

Requests to `GET /api/user/enquiries?limit=20&offset=0` use the HttpOnly session
cookie with same-origin credentials and no-store caching. No token is read or stored
by JavaScript. A 401 clears displayed records and offers login; SessionShell retains
its existing expiry/logout redirect behavior. A 403 displays `You do not have permission`
without rendering the response body. Bearer API clients remain supported by the backend.

The API order is preserved. Previous/Next use 20-row pages and the API's maximum
offset of 10000. Without a total count, an exactly full final page permits one extra
Next request, which shows an empty page with Previous available. Concurrent inserts
can shift offset pages; use Refresh to return to the latest first page.

Private rows are cleared before loading and on errors. Stale/aborted responses
cannot populate a different session's screen. Tab focus and SessionContext identity changes revalidate;
no polling or activity refresh is added. Revocation while a page remains untouched
is discovered at its next request. No personal data is persisted by the component.
Trusted-host/public-origin configuration and HTTPS cookie verification remain deployment requirements.

Run `node tests/coordinator-enquiries.mjs` with the same browser prerequisites as
the public form test. Twelve real-Chrome scenarios use mocked APIs in an owned,
temporary Next.js app. They cover access denial, stale sessions, fields/order,
pagination, loading/errors/retry, text-only rendering and mobile layout. They do not
verify real PostgreSQL, gateway routing or deployed authorization. Run TypeScript and a production build alongside these focused component checks.
A full accessibility audit remains a separate integration check.


Server-side 422 errors queue focus until React has re-enabled the fieldset.
The public-form regression suite includes delayed responses for name, contact,
message and consent, checking enabled state, focus and accessible error references.
