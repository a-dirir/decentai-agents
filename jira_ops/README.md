# Jira Ops agent

This is the focused DecentAI replacement for the standalone
`Jira-Ops-Terminal-Assistant` script.

Create one `Jira Cloud Connection` secret after installation with:

- `base_url`: for example `https://example.atlassian.net`
- `email`: the Atlassian account email
- `api_token`: an Atlassian API token
- optional Jira custom field ids for Time to Resolution and Customer Informed

The agent reads queues and issue details at permission level 0. Every Jira
write—internal comment, worklog, or transition—is permission level 3 and
therefore requires explicit approval in a normal chat.

The old terminal bot's polling loops, Windows UI, browser launching, Slack
webhooks, automatic validation, and multi-step bulk resolution are
intentionally excluded. They are scheduler/automation concerns and are not
safe or reliable inside an on-demand conversational agent.
