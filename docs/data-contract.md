# Watari canonical data contract v1

Status: frozen for the private-pilot implementation. Changes to canonical bytes,
digest framing, identifiers, or fixture results require a new contract version;
they are never silent in-place changes.

This document freezes the logical representation only. The physical object layout is intentionally undecided:
loose files, packs, Git object placement,
encryption envelopes, and compression remain qualification decisions in D010
and D011.

## 1. Contract boundary

The v1 pipeline is:

1. parse without losing duplicate object names;
2. apply Watari string and schema normalization;
3. validate the v1 JSON profile and the relevant record schema;
4. serialize the normalized value with RFC 8785 JSON Canonicalization Scheme
   (JCS) rules;
5. hash the resulting bytes with the purpose-specific frame in section 6.

An implementation MUST fail closed before committing when any step fails. It
MUST NOT repair an already signed or stored event in place.

RFC 8785 does not itself perform Unicode normalization. Watari performs Unicode
NFC and newline normalization before JCS, then requires JCS to preserve the
normalized strings exactly. This ordering is part of v1.

## 2. Memory event envelope

Every v1 memory event has exactly these top-level members. Schema validators
reject unknown or missing members.

| Member | v1 type and rule |
| --- | --- |
| `schema_version` | integer `1` |
| `event_id` | derived `watari-event-v1:` identifier from section 7 |
| `event_type` | `memory`, `correction`, or `tombstone` |
| `recorded_at` | canonical timestamp; always present |
| `observed_at` | canonical timestamp or `null` when the source did not provide one |
| `payload_schema` | versioned, allowlisted schema identifier |
| `payload` | value accepted by that payload schema and section 4 |
| `payload_digest` | derived `watari-payload-v1:` digest |
| `visibility` | `local-only`, `trusted-model`, or `low-risk-model` |
| `source` | source-binding object below |
| `creator` | creator object below |
| `supersedes` | prior event ID or `null` |

The source-binding object has exactly:

| Member | v1 type and rule |
| --- | --- |
| `connector_instance_id` | opaque globally unique non-secret string |
| `stable_source_event_digest` | opaque typed digest; never a raw provider ID |
| `dream_run_id` | opaque run ID for dream-created events, otherwise `null` |

The creator object has exactly:

| Member | v1 type and rule |
| --- | --- |
| `kind` | `manual`, `migration`, or `dream` |
| `model_policy_digest` | typed policy digest for `dream`, otherwise a typed digest or `null` |

For `memory`, `supersedes` is `null`. For `correction` and `tombstone`, it is a
different, existing event ID. A `dream` creator requires non-null
`dream_run_id` and `model_policy_digest`; other creator kinds require a null
`dream_run_id`. Referential, cycle, and authorization checks are transaction
rules owned by D004, not canonicalization rules.

Typed v1 logical digests use their purpose prefix followed by exactly 64
lowercase hexadecimal characters. This includes `watari-event-v1:`,
`watari-payload-v1:`, `watari-envelope-v1:`, `watari-source-v1:`, and
`watari-policy-v1:` values. Payload and context schema identifiers are resolved
against an explicit versioned allowlist before hashing; unknown identifiers
fail closed.

Raw source text, credentials, provider event IDs, and absolute host paths are
not valid envelope data. A payload digest is stored inside the encrypted logical
state; it is not a permitted plaintext remote object name.

Logical `event_id`, payload digest, and envelope digest values do not authorize
plaintext remote filenames. D010 and D011 must keep them inside authenticated
encrypted state and derive any visible remote locator from ciphertext bytes or
a qualified keyed HMAC. A logical identifier may not be exposed remotely merely
because it is a digest.

## 3. String normalization

Normalization applies recursively to every JSON string, including object names:

1. replace each CRLF pair with LF;
2. replace every remaining CR with LF;
3. normalize the result to Unicode NFC.

The normalized value is the value that is schema-validated and serialized.
Duplicate names in the parsed input are invalid. If two distinct input names
become equal after newline or Unicode NFC normalization, the value is also
invalid. Neither case may use first-wins or last-wins behavior.

V1 freezes the normalization and character-assignment dataset to Unicode
15.0.0. Code points unassigned in Unicode 15.0.0 are rejected even when a newer
host library assigns them. Implementations must use the frozen table rather than
silently inheriting their host Unicode version. A newer normalization engine is
permitted only for code points assigned in 15.0.0, for which Unicode
normalization stability preserves the v1 result.

The NFC engine itself must implement Unicode 15.0.0 or newer. An older engine
fails closed even when the assignment table is present, because Unicode 15
combining classes affect canonical ordering. `T-CANON-038` fixes the observable
ordering of U+1E4EC and U+1E4EE so that this requirement cannot degrade into a
version-string check alone.

`tests/fixtures/canonical/unicode-15.0.0-assigned-ranges.json` is that frozen
assignment table. Its v1 SHA-256 is
`5f50a0fa5ed02570bfb970ec6e6c81899e3482843bcdeb9a4d2776af805cf76b`.
Changing the table or digest requires a new canonical contract version.

Lone UTF-16 surrogate code points, Unicode 15.0.0 unassigned code points, and
any value not expressible as valid Unicode are invalid. UTF-8 output uses no BOM
and has no trailing LF beyond a newline that is data inside a JSON string.

## 4. Watari v1 JSON profile

Allowed JSON values are `null`, booleans, strings, arrays, objects, and integers
from `-9007199254740991` through `9007199254740991`, inclusive. Object names are
strings. Arrays retain their order.

Floating-point values are forbidden, including mathematically integral values
such as `1.0`, as well as NaN and infinities. Counts use JSON integers in the
safe range. Values requiring decimal semantics, such as money, use a
schema-declared decimal string plus any separately required unit or currency.

A canonical decimal string matches this grammar:

```text
0 | 0.[0-9]*[1-9] | [1-9][0-9]*(.[0-9]*[1-9])? |
-( [1-9][0-9]*(.[0-9]*[1-9])? | 0.[0-9]*[1-9] )
```

Spaces in the display above are not part of the value. A plus sign, exponent,
leading zero, trailing fractional zero, bare decimal point, and negative zero
are forbidden in canonical state.

The common ingress normalizer accepts only the string grammar
`-?(0|[1-9][0-9]*)(.[0-9]+)?`. It removes trailing fractional zeroes and then a
vacant decimal point; any negative zero becomes `0`. Thus ingress `1.20`
becomes canonical `1.2`, and `-0.00` becomes `0`. Plus signs, exponents, leading
zeroes, bare decimal points, non-string numeric values, and locale separators
are rejected rather than guessed. The canonical JSON layer treats the result as
a string; the payload schema declares which fields use this normalizer.

## 5. Timestamp profile

Canonical timestamps are UTC RFC 3339 strings with exactly six fractional
second digits:

```text
YYYY-MM-DDTHH:MM:SS.ffffffZ
```

The common ingress normalizer accepts uppercase RFC 3339 calendar date and time,
optional one-to-six fractional digits, and an explicit `Z` or `±HH:MM` offset.
It converts the represented instant to UTC and zero-fills to six fractional
digits. Precision finer than microseconds is rejected rather than rounded.
Unknown offset `-00:00`, leap seconds, absent offsets, lowercase `t`/`z`, and
out-of-range dates or offsets are rejected. A missing observation is represented
by JSON `null`, never by the current clock. Tests use fixed timestamps.

## 6. Canonical JSON bytes and digest frame

After sections 3 through 5, serialization follows RFC 8785:

- no whitespace is emitted between JSON tokens;
- strings use JCS escaping and invalid Unicode terminates processing;
- object names are sorted recursively by their unescaped UTF-16 code units as
  unsigned integers, independent of locale;
- array order is preserved while objects inside arrays are sorted;
- the result is encoded as UTF-8 without BOM or a trailing separator.

Watari's integer-only profile avoids language-dependent IEEE 754 rendering but
otherwise produces RFC 8785-compatible bytes.

All v1 digests use SHA-256 over this exact binary frame:

```text
ASCII("WATARI") || 0x00 || ASCII(domain) || 0x00 ||
  uint64be(len(part_1)) || part_1 ||
  ... ||
  uint64be(len(part_n)) || part_n
```

`len` is the octet length, not a character count. There are no implicit parts.
The first bytes can equivalently be written `WATARI\x00`. Domain strings and
external encodings are:

| Purpose | Domain | External lowercase-hex prefix |
| --- | --- | --- |
| canonical payload | `payload/v1` | `watari-payload-v1:` |
| event identity | `event-id/v1` | `watari-event-v1:` |
| complete logical envelope | `event-envelope/v1` | `watari-envelope-v1:` |
| canonical context | `context-fingerprint/canonical/v1` | `watari-context-canonical-v1:` |
| effective context | `context-fingerprint/effective/v1` | `watari-context-effective-v1:` |

An external digest is its table prefix followed by exactly 64 lowercase
hexadecimal characters. Purpose prefixes are not part of the hashed frame.

## 7. Payload digest, event ID, and envelope digest

The payload digest is:

```text
H("payload/v1", canonical_bytes(payload))
```

The event identity projection is an object with exactly these members:

```json
{
  "connector_instance_id": "opaque connector instance",
  "event_type": "memory",
  "payload_digest": "watari-payload-v1:...",
  "payload_schema": "watari.memory.fact/v1",
  "schema_version": 1,
  "stable_source_event_digest": "opaque typed source digest"
}
```

The event ID is:

```text
H("event-id/v1", canonical_bytes(identity_projection))
```

Both the envelope `schema_version` and `payload_schema` participate in identity.
The same JSON value under two payload schemas therefore receives two event IDs;
it is not misclassified as a same-ID envelope conflict.

The complete logical envelope digest is:

```text
H("event-envelope/v1", canonical_bytes(envelope_with_event_id))
```

The envelope digest is integrity metadata and is not a member of the envelope.
Two envelopes with the same event ID but different canonical envelope bytes are
a conflict to quarantine; they are never last-writer-wins updates. Correction
and tombstone records receive new event IDs and point to the earlier ID through
`supersedes`.

Generation of `stable_source_event_digest`, its keyed construction, and key
rotation belong to D010. D003 only requires an opaque, stable, typed value as
event-ID input. A raw provider identifier or an unkeyed digest that permits
dictionary recovery must not be substituted.

## 8. Context fingerprints

The context compiler produces a schema-validated policy/revision manifest and
the exact context bytes for a projection. The manifest is normalized and
canonicalized under sections 3 through 6. The context bytes are the bytes that
will actually cross the runtime boundary and are not decoded, normalized, or
re-serialized by the fingerprint function.

The v1 manifest has exactly these members; unknown or missing members fail
closed:

| Member | v1 rule |
| --- | --- |
| `schema_version` | integer `1` |
| `context_schema` | allowlisted `watari.context/v1` |
| `projection_kind` | `canonical` or `effective`, matching the selected hash domain |
| `policy_revision` | nonempty immutable revision ID |
| `profile_revision` | nonempty immutable revision ID |
| `memory_revision` | nonempty immutable revision ID |
| `project_revision` | nonempty immutable revision ID or `null` |
| `visibility` | `local-only`, `trusted-model`, or `low-risk-model` |
| `route_policy_digest` | `watari-route-policy-v1:` plus 64 lowercase hex characters |

For projection kind `canonical` or `effective`:

```text
H("context-fingerprint/" + kind + "/v1",
  canonical_bytes(policy_revision_manifest),
  exact_context_bytes)
```

Before hashing, the function validates the exact manifest version and requires
`projection_kind` to equal the selected domain. C004 supplies the revision
values but may not change this shape without a new manifest version. Adding,
removing, or changing a manifest member changes the fingerprint. Canonical and
effective projections cannot collide because they use different domains and
prefixes. NFD versus NFC, LF versus CRLF, and a final newline versus no final
newline remain different when they occur in exact context bytes.

## 9. Golden vectors and conformance

`tests/fixtures/canonical/vectors.json` is the v1 cross-language source of truth.
It is parsed with duplicate-name detection rather than an ordinary last-wins
JSON loader. Its synthetic success vectors cover Unicode NFC and LF
normalization, UTF-16 property sorting, JCS escaping, safe integers, scalar
ingress normalization, digest framing, a complete event, and both context
projection domains. Its rejection vectors cover unknown versions and schemas,
unknown or missing members, source/creator/supersedes violations, malformed
typed digests, identity mismatches, and context domain mismatches.

A conforming implementation must reproduce every byte and digest exactly and
must reject duplicate names, normalization collisions, invalid Unicode,
floating-point values, unsafe integers, non-canonical timestamps, and invalid
schema values. Unknown contract, event, payload, or manifest versions fail
closed. Golden-vector changes require a versioned contract migration and an
independent high-trust review.

## References

- [RFC 8785: JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html)
- [Unicode 15.0.0](https://www.unicode.org/versions/Unicode15.0.0/)
