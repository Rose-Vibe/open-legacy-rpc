# Conformance Test Suite — Original Description (verbatim)

> From Rose, 2026-06-26

Okay, so we wrote our impl in python because the main goal was to have an open reference implementation, but really I'd like projects to be able to use the language of their choice.

I think the best way to achieve this is a set of unit and conformance tests written in Python.

---

Encoding/serde unit tests:
- We want to test all of the encodings and serialization. This is both for individual RPC types and for stuff like the huffman encoding or the hashes.
- I think we should have two kinds: preset tests that cover basics and known edge cases, and randomly generated tests that add random values.
- I think we should have a script that can generate and validate any test case.
    - Generate: choose basic or random, outputs an array of test cases
    - Validate: give it your array of test cases and array of results, it gives you back a pass/fail array where each object includes the reasons array for what was wrong with it.
- I think we should standardize on a common format with a declared json schema.
    - Each test generation includes:
        - Test info
            - Test id (random, for req/resp correlation at the validate step)
            - Test name
            - Test description
        - Test input data
            - Test input data is test-type specific — a discriminated union of all of the supported tests.
    - Each test response includes:
        - Test info
        - Test input data
        - Test output data
            - also test-type specific discriminated union. Binary can be included as `dataHex`
    - Each test validation includes:
        - Test info
        - Test input data
        - Test output data
        - Test validation info
            - pass/fail
            - list of fail reasons
    - Effectively, each stage adds data to the same object so each stage can be completed statelessly, and every stage can be effortlessly analyzed without having to manually keep track of the data (since e.g. validation response includes every part of it so it's easy to figure out what's wrong)

Use:
- `legacy-net-serde-test generate {category} {basic/random}` -> array of test generations to stdout
- `legacy-net-serde-test validate` + test responses -> array of test validations to stdout

---

Server/client tests:
- **Launches a real unity legacy networking server/client implemented in python**
- takes input from stdin for the type of test it should run
- test steps tell the new implementation what to do — the new impl is expected to be able to dynamically follow the steps
- server/client process outputs pass/fail info to stdout, and exits on the first failure
    - test info
        - test id
        - test name
        - test description
    - validation info
        - pass/fail
        - failures list

Server/client tests generator:
- generates an array of json to give to the server/client test runner
- each can be passed to the runner to start the test
- Schema for stdout json format for every test type
    - test info
        - test id
        - test name
        - test description
    - test steps
        - list of steps
        - test step discriminated union
        - some steps are python test runner-only some are tested impl only

Use:
1. Generate tests `legacy-net-peer-test generate {category} {basic/random}`
2. Run server and test against it
    1. `legacy-net-peer-test run` + give it stdin, run in background and exit tests if it exits
    2. Follow steps to run tested impl-side code; assert after each step that peer test is still running, err if it errored so the test fails
    3. Close peer test if exited early for our own err

---

Real unity server/client:
- Much more basic. Multiple pre built scenarios with preset steps the impl should follow to test behavior and edge cases. Should mirror one of the basic python runner server/client tests so the impl can go back and use the python version to diagnose what's wrong in more detail
- Since these are preset, tested impl just builds a test script to do what it should (maybe we even use a hardcoded steps array to reuse code?), runs the server/client, and makes sure both edit cleanly.
