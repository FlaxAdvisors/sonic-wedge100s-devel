# LED Breakout Partial-State Encoding - Follow-up

**Date:** 2026-04-09
**Related:** GAP-028, Task 5 (led-pipeline)

## Problem

The LEDUP1 patched bytecode program in
`device/accton/x86_64-accton_wedge100s_32x-r0/led_proc_init.soc` only
distinguishes 0x00 (dark) from 0x80 (solid-on). It does not implement
a blink encoding for partial breakout state.

## Current Workaround

`_aggregate_led_states()` in `wedge100s-ledup-linkstate` maps both
all-up and partial-up to 0x80. Effect: in a 4x25G breakout, if 3 of 4
lanes are up, the LED shows solid-on, indistinguishable from all 4 up.

## Fix (Future Work)

Extend the LEDUP1 bytecode (`led 1 prog` in `led_proc_init.soc`) to
decode bit 0 of the data byte as a blink flag. Testing required on
hardware with partial-link breakout scenarios. Bytecode reverse-
engineering is nontrivial - requires understanding the op table and
the interaction with LEDUP0 (blue channel).

Once the bytecode is extended, update `_aggregate_led_states()`:
change the FIXME branch from `0x80` to `0x81` and update the docstring.

## Scope

`wedge100s/led-pipeline` topic branch owns both the Python daemon and
(indirectly) the LED bytecode via `led_proc_init.soc`. Note that
`led_proc_init.soc` is technically owned by `wedge100s/chipset-config`
per the workflow - the fix will need coordination across both branches.
