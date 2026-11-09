- A check that gets no answer (a dropped connection, a 502) no longer ends
  on "Recognition server not reachable". The page waits for the server's
  health check ("The checker is starting again"), then offers the same
  photo once more on a tap ("The checker is ready"). The same photo dropped
  a second time gets "We could not check this photo" and is not offered
  again. New outcome codes: `server_restarting`, `server_back`,
  `check_failed_twice` (frontend/README.md).
