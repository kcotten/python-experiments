#!/usr/bin/env python3
"""
Automated Daily Standup Generator
Pulls data from GitHub, Jira, and personal notes to create Slack standup posts
"""

import argparse
import json
import os
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Optional

import requests


class StandupGenerator:
    def __init__(self, config_file: str = "standup_config.json"):
        """Initialize with configuration file"""
        self.config = self.load_config(config_file)
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.jira_token = os.getenv("JIRA_TOKEN")
        self.slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.confluence_token = os.getenv("CONFLUENCE_TOKEN")

    def load_config(self, config_file: str) -> dict:
        """Load configuration from JSON file"""
        try:
            with open(config_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return self.create_default_config(config_file)

    def create_default_config(self, config_file: str) -> dict:
        """Create default configuration file"""
        default_config = {
            "github": {
                "username": "your-username",
                "repos": ["org/repo1", "org/repo2"],
                "include_prs": True,
                "include_commits": True,
                "include_reviews": True,
            },
            "jira": {
                "base_url": "https://your-org.atlassian.net",
                "username": "your-email@company.com",
                "project_keys": ["PROJ", "TEAM"],
                "include_completed": True,
                "include_in_progress": True,
            },
            "notes": {"file_path": "./daily_notes.md", "format": "markdown"},
            "slack": {
                "channel": "#standup",
                "username": "Standup Bot",
                "icon_emoji": ":robot_face:",
            },
            "ai_summary": {
                "enabled": True,
                "provider": "none",  # "openai", "anthropic", or "none"
                "model": "gpt-4o-mini",  # or "claude-3-haiku-20240307"
                "prompt_style": "professional",  # "professional", "casual", or "detailed"
            },
        }

        with open(config_file, "w") as f:
            json.dump(default_config, f, indent=2)

        print(
            f"Created default config at {config_file}. Please update with your details."
        )
        return default_config

    def get_last_workday(self) -> str:
        """Get the last workday (handles weekends)"""
        today = datetime.now()

        # If Monday, look back to Friday
        if today.weekday() == 0:  # Monday
            last_workday = today - timedelta(days=3)
        # If Tuesday-Friday, look back 1 day
        elif today.weekday() in [1, 2, 3, 4]:  # Tuesday-Friday
            last_workday = today - timedelta(days=1)
        # If Saturday, look back to Friday
        elif today.weekday() == 5:  # Saturday
            last_workday = today - timedelta(days=1)
        # If Sunday, look back to Friday
        else:  # Sunday
            last_workday = today - timedelta(days=2)

        return last_workday.strftime("%Y-%m-%d")

    def get_github_activity(self) -> dict:
        """Fetch GitHub activity since last workday"""
        if not self.github_token:
            return {"error": "GitHub token not found"}

        last_workday = self.get_last_workday()
        today = datetime.now().strftime("%Y-%m-%d")
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        username = self.config["github"]["username"]
        repos = self.config["github"]["repos"]

        activity: dict[str, list[dict]] = {
            "commits": [],
            "prs_opened": [],
            "prs_merged": [],
            "reviews": [],
        }

        for repo in repos:
            activity["commits"].extend(
                self._fetch_github_commits(
                    repo, headers, username, last_workday, today
                )
            )

        for repo in repos:
            opened, merged = self._fetch_github_prs(
                repo, headers, username, last_workday
            )
            activity["prs_opened"].extend(opened)
            activity["prs_merged"].extend(merged)

        activity["reviews"] = self._fetch_github_reviews(
            headers, username, last_workday
        )

        return activity

    def _fetch_github_commits(
        self,
        repo: str,
        headers: dict,
        username: str,
        last_workday: str,
        today: str,
    ) -> list[dict]:
        """Fetch the user's commits for one repo in the date window"""
        commits: list[dict] = []
        url = f"https://api.github.com/repos/{repo}/commits"
        params = {
            "author": username,
            "since": f"{last_workday}T00:00:00Z",
            "until": f"{today}T00:00:00Z",
        }

        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                for commit in response.json():
                    commits.append(
                        {
                            "repo": repo,
                            "message": commit["commit"]["message"].split("\n")[
                                0
                            ],
                            "sha": commit["sha"][:7],
                            "url": commit["html_url"],
                        }
                    )
        except Exception as e:
            print(f"Error fetching commits for {repo}: {e}")

        return commits

    def _fetch_github_prs(
        self, repo: str, headers: dict, username: str, last_workday: str
    ) -> tuple[list[dict], list[dict]]:
        """Fetch the user's PRs opened and merged since last workday"""
        opened: list[dict] = []
        merged: list[dict] = []
        since = f"{last_workday}T00:00:00Z"
        url = f"https://api.github.com/repos/{repo}/pulls"
        params = {
            "state": "all",
            "sort": "created",
            "direction": "desc",
            "per_page": 100,
        }

        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                for pr in response.json():
                    if pr["user"]["login"] != username:
                        continue

                    summary = {
                        "title": pr["title"],
                        "repo": repo,
                        "url": pr["html_url"],
                        "number": pr["number"],
                    }
                    if pr["created_at"] >= since:
                        opened.append(
                            {**summary, "created_at": pr["created_at"]}
                        )
                    if pr["merged_at"] and pr["merged_at"] >= since:
                        merged.append({**summary, "merged_at": pr["merged_at"]})
        except Exception as e:
            print(f"Error fetching PRs for {repo}: {e}")

        return opened, merged

    def _fetch_github_reviews(
        self, headers: dict, username: str, last_workday: str
    ) -> list[dict]:
        """Fetch PRs the user reviewed since last workday"""
        reviews: list[dict] = []

        try:
            # Use search API for reviews (this is the best way to find reviews by user)
            search_url = "https://api.github.com/search/issues"
            params = {
                "q": f"type:pr reviewed-by:{username} updated:>={last_workday}",
                "sort": "updated",
                "order": "desc",
                "per_page": 50,
            }
            response = requests.get(search_url, headers=headers, params=params)
            if response.status_code == 200:
                for pr in response.json().get("items", []):
                    # Get the repo name from the URL
                    repo_parts = pr["repository_url"].split("/")
                    reviews.append(
                        {
                            "title": pr["title"],
                            "repo": f"{repo_parts[-2]}/{repo_parts[-1]}",
                            "url": pr["html_url"],
                            "number": pr["number"],
                        }
                    )
        except Exception as e:
            print(f"Error fetching PR reviews: {e}")

        return reviews

    def get_jira_activity(self) -> dict:
        """Fetch Jira activity since last workday"""
        if not self.jira_token:
            return {"error": "Jira token not found"}

        base_url = self.config["jira"]["base_url"]
        username = self.config["jira"]["username"]

        # Use Basic Auth with email:token
        import base64

        auth_string = f"{username}:{self.jira_token}"
        auth_bytes = auth_string.encode("ascii")
        auth_b64 = base64.b64encode(auth_bytes).decode("ascii")

        headers = {
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/json",
        }

        last_workday = self.get_last_workday()

        activity = {"completed": [], "updated": [], "in_progress": []}

        # JQL query for tickets updated since last workday
        jql = f'assignee = currentUser() AND updated >= "{last_workday}" ORDER BY updated DESC'

        url = f"{base_url}/rest/api/3/search"
        params = {
            "jql": jql,
            "fields": "key,summary,status,updated",
            "maxResults": 50,
        }

        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                issues = response.json().get("issues", [])
                for issue in issues:
                    ticket = {
                        "key": issue["key"],
                        "summary": issue["fields"]["summary"],
                        "status": issue["fields"]["status"]["name"],
                        "url": f"{base_url}/browse/{issue['key']}",
                    }

                    status = issue["fields"]["status"]["name"].lower()
                    if (
                        "done" in status
                        or "resolved" in status
                        or "closed" in status
                    ):
                        activity["completed"].append(ticket)
                    elif "progress" in status or "review" in status:
                        activity["in_progress"].append(ticket)
                    else:
                        activity["updated"].append(ticket)
        except Exception as e:
            print(f"Error fetching Jira tickets: {e}")

        return activity

    def get_personal_notes(self) -> dict[str, list[str]]:
        """Read personal notes from file, separating completed items and today's plan"""
        notes_file = self.config["notes"]["file_path"]

        if not os.path.exists(notes_file):
            return {"completed": [], "plan": []}

        try:
            with open(notes_file, "r") as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading notes file: {e}")
            return {"completed": [], "plan": []}

        last_workday = datetime.strptime(self.get_last_workday(), "%Y-%m-%d")
        return self._parse_notes(content, last_workday, datetime.now())

    @staticmethod
    def _is_date_header(line: str) -> bool:
        """True for '##' lines that look like they carry a 2024/2025 date"""
        return line.startswith("##") and any(
            year in line for year in ("2025-", "2024-")
        )

    @staticmethod
    def _parse_header_date(line: str) -> Optional[datetime]:
        """Extract the first YYYY-MM-DD word from a header line"""
        for word in line.split():
            if "-" in word and len(word) == 10:
                try:
                    return datetime.strptime(word, "%Y-%m-%d")
                except ValueError:
                    continue
        return None

    @staticmethod
    def _section_from_header(line: str) -> Optional[str]:
        """Map a '###' subsection header to 'completed', 'plan' or None"""
        lowered = line.lower()
        if "completed" in lowered:
            return "completed"
        if "plan" in lowered:
            return "plan"
        return None

    @staticmethod
    def _bullet_text(line: str) -> Optional[str]:
        """Return the text of a markdown bullet line, or None if not a bullet"""
        if line.startswith(("- ", "* ", "+ ")):
            return line[2:]
        return None

    def _parse_notes(
        self, content: str, last_workday: datetime, today: datetime
    ) -> dict[str, list[str]]:
        """Collect completed items since last_workday and today's plan"""
        result: dict[str, list[str]] = {"completed": [], "plan": []}
        current_date: Optional[datetime] = None
        current_section: Optional[str] = None  # 'completed', 'plan', or None
        capture_mode = False

        for raw_line in content.split("\n"):
            line = raw_line.strip()

            if self._is_date_header(line):
                parsed = self._parse_header_date(line)
                if parsed:
                    current_date = parsed
                    capture_mode = parsed >= last_workday
                    current_section = None  # Reset section on new date
                continue

            if line.startswith("###"):
                current_section = self._section_from_header(line)
                continue

            item = self._bullet_text(line)
            if item is None or not capture_mode:
                continue

            if current_section is None:
                # Legacy format (no subsections) - treat as completed
                result["completed"].append(item)
            elif current_section == "completed":
                result["completed"].append(item)
            elif (
                current_section == "plan"
                and current_date
                and current_date.date() == today.date()
            ):
                # Only today's date contributes to the plan
                result["plan"].append(item)

        return result

    def get_confluence_activity(self) -> dict:
        """Fetch Confluence activity since last workday"""
        if not self.confluence_token:
            return {"error": "Confluence token not found"}

        base_url = self.config["confluence"]["base_url"]
        username = self.config["confluence"]["username"]

        # Use Basic Auth with email:token (same as Jira)
        import base64

        auth_string = f"{username}:{self.confluence_token}"
        auth_bytes = auth_string.encode("ascii")
        auth_b64 = base64.b64encode(auth_bytes).decode("ascii")

        headers = {
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/json",
        }

        last_workday = self.get_last_workday()
        print(f"[DEBUG] Confluence: Looking for activity since {last_workday}")
        print(f"[DEBUG] Confluence: Base URL: {base_url}")
        print(f"[DEBUG] Confluence: Username: {username}")

        activity = {"created": [], "updated": []}

        try:
            # Search for pages created by current user since last workday
            url = f"{base_url}/wiki/rest/api/content/search"

            # Try a broader search first - all pages created by user (no date filter)
            cql_test = 'creator = currentUser() AND type = "page"'
            params_test = {
                "cql": cql_test,
                "expand": "space,version,history",
                "limit": 10,
            }

            print(f"[DEBUG] Testing broad CQL: {cql_test}")
            response = requests.get(url, headers=headers, params=params_test)
            print(f"[DEBUG] Test response status: {response.status_code}")

            if response.status_code == 200:
                test_results = response.json()
                print(
                    f"[DEBUG] Total pages found (no date filter): {len(test_results.get('results', []))}"
                )
                for page in test_results.get("results", [])[:3]:
                    created_date = page.get("history", {}).get(
                        "createdDate", "Unknown"
                    )
                    print(
                        f"[DEBUG] Sample page: '{page['title']}' created: {created_date}"
                    )
            else:
                print(f"[DEBUG] Test query failed: {response.text}")
                return {"error": f"Test query failed: {response.status_code}"}

            # Now try with date filter
            cql_created = f'creator = currentUser() AND created >= "{last_workday}" AND type = "page"'
            params = {
                "cql": cql_created,
                "expand": "space,version,history",
                "limit": 50,
            }

            print(f"[DEBUG] CQL with date filter: {cql_created}")
            response = requests.get(url, headers=headers, params=params)
            print(
                f"[DEBUG] Date-filtered response status: {response.status_code}"
            )

            if response.status_code == 200:
                results = response.json().get("results", [])
                print(
                    f"[DEBUG] Pages created since {last_workday}: {len(results)}"
                )
                for page in results:
                    print(
                        f"[DEBUG] Found created page: '{page['title']}' in space: {page['space']['name']}"
                    )
                    activity["created"].append(
                        {
                            "id": page["id"],
                            "title": page["title"],
                            "space": page["space"]["name"],
                            "url": f"{base_url}/wiki{page['_links']['webui']}",
                            "created": page["history"]["createdDate"],
                        }
                    )
            else:
                print(f"[DEBUG] Created pages query failed: {response.text}")

            # Search for pages updated by current user since last workday
            cql_updated = f'contributor = currentUser() AND lastModified >= "{last_workday}" AND type = "page"'
            params = {
                "cql": cql_updated,
                "expand": "space,version,history",
                "limit": 50,
            }

            print(f"[DEBUG] CQL for updates: {cql_updated}")
            response = requests.get(url, headers=headers, params=params)
            print(
                f"[DEBUG] Updated pages response status: {response.status_code}"
            )

            if response.status_code == 200:
                results = response.json().get("results", [])
                print(
                    f"[DEBUG] Pages updated since {last_workday}: {len(results)}"
                )
                for page in results:
                    print(
                        f"[DEBUG] Found updated page: '{page['title']}' in space: {page['space']['name']}"
                    )
                    activity["updated"].append(
                        {
                            "id": page["id"],
                            "title": page["title"],
                            "space": page["space"]["name"],
                            "url": f"{base_url}/wiki{page['_links']['webui']}",
                            "updated": page["version"]["when"],
                        }
                    )
            else:
                print(f"[DEBUG] Updated pages query failed: {response.text}")

        except Exception as e:
            print(f"[DEBUG] Exception in Confluence activity: {e}")
            return {"error": str(e)}

        print(
            f"[DEBUG] Final activity: {len(activity['created'])} created, {len(activity['updated'])} updated"
        )
        return activity

    @staticmethod
    def _has_data(data: dict) -> bool:
        """True if a source returned data rather than nothing or an error"""
        return bool(data) and "error" not in data

    def _header_info(self) -> tuple[str, str]:
        """Return (date_range, period_label) for the standup header"""
        today = datetime.now()
        last_workday = datetime.strptime(self.get_last_workday(), "%Y-%m-%d")

        if today.weekday() == 0:  # Monday
            date_range = f"{last_workday.strftime('%A, %B %d')} - {today.strftime('%A, %B %d, %Y')}"
            return date_range, "Since Friday"
        return today.strftime("%A, %B %d, %Y"), "Yesterday's Progress"

    @staticmethod
    def _plan_lines(notes: dict) -> list[str]:
        """Today's plan items, or a placeholder if there are none"""
        return notes.get("plan") or ["_Add your planned work here_"]

    @staticmethod
    def _section(
        title: str,
        items: list[dict],
        format_item: Callable[[dict], str],
        limit: Optional[int] = None,
    ) -> list[tuple[str, list[str]]]:
        """Build a (title, lines) section, or nothing if items is empty"""
        if not items:
            return []
        return [(title, [format_item(item) for item in items[:limit]])]

    @staticmethod
    def _pr_line(pr: dict) -> str:
        return f"<{pr['url']}|#{pr['number']}: {pr['title']}>"

    @staticmethod
    def _ticket_line(ticket: dict) -> str:
        return f"<{ticket['url']}|{ticket['key']}> {ticket['summary']}"

    @staticmethod
    def _ticket_status_line(ticket: dict) -> str:
        return (
            f"<{ticket['url']}|{ticket['key']}> "
            f"{ticket['summary']} ({ticket['status']})"
        )

    @staticmethod
    def _page_line(page: dict) -> str:
        return f"<{page['url']}|{page['title']}> ({page['space']})"

    def _github_sections(
        self, data: dict, commit_line: Callable[[dict], str]
    ) -> list[tuple[str, list[str]]]:
        return (
            self._section(
                "GitHub Commits:", data.get("commits", []), commit_line, 5
            )
            + self._section(
                "PRs Merged:", data.get("prs_merged", []), self._pr_line
            )
            + self._section(
                "PRs Opened:", data.get("prs_opened", []), self._pr_line
            )
            + self._section(
                "Code Reviews:", data.get("reviews", []), self._pr_line, 5
            )
        )

    def _jira_sections(self, data: dict) -> list[tuple[str, list[str]]]:
        return (
            self._section(
                "Jira - Completed:",
                data.get("completed", []),
                self._ticket_line,
            )
            + self._section(
                "Jira - Updated:",
                data.get("updated", []),
                self._ticket_status_line,
                3,
            )
            + self._section(
                "Jira - In Progress:",
                data.get("in_progress", []),
                self._ticket_line,
                3,
            )
        )

    def _confluence_sections(self, data: dict) -> list[tuple[str, list[str]]]:
        return self._section(
            "Confluence - Created:", data.get("created", []), self._page_line
        ) + self._section(
            "Confluence - Updated:", data.get("updated", []), self._page_line, 3
        )

    def _activity_sections(
        self,
        github_data: dict,
        jira_data: dict,
        confluence_data: dict,
        notes: dict,
        commit_line: Callable[[dict], str],
        notes_limit: Optional[int] = None,
    ) -> list[tuple[str, list[str]]]:
        """Collect (title, lines) sections from every source with data"""
        sections: list[tuple[str, list[str]]] = []
        if self._has_data(github_data):
            sections += self._github_sections(github_data, commit_line)
        if self._has_data(jira_data):
            sections += self._jira_sections(jira_data)
        if self._has_data(confluence_data):
            sections += self._confluence_sections(confluence_data)
        if notes.get("completed"):
            sections.append(
                ("Recent Activity Summary:", notes["completed"][:notes_limit])
            )
        return sections

    def format_standup_message(
        self,
        github_data: dict,
        jira_data: dict,
        confluence_data: dict,
        notes: dict,
        ai_summary: Optional[str] = None,
    ) -> str:
        """Format all data into a standup message (fallback text format)"""
        date_range, period = self._header_info()
        parts = [f"## Daily Standup - {date_range}\n", f"### {period}"]

        if ai_summary and ai_summary.strip():
            parts.append(f"{ai_summary}\n")
        else:
            # Fallback: Use detailed breakdown if no AI summary
            sections = self._activity_sections(
                github_data,
                jira_data,
                confluence_data,
                notes,
                lambda c: f"[{c['repo']}] {c['message']} ({c['sha']})",
            )
            for title, lines in sections:
                parts.append(f"\n**{title}**")
                parts.extend(f"• {line}" for line in lines)

        parts.append("\n### Today's Plan")
        parts.extend(f"• {line}" for line in self._plan_lines(notes))

        parts.append("\n### Blockers")
        parts.append("• None")

        return "\n".join(parts)

    @staticmethod
    def _mrkdwn_section(text: str) -> dict:
        return {"type": "section", "text": {"type": "mrkdwn", "text": text}}

    def _blocks_progress_text(
        self,
        github_data: dict,
        jira_data: dict,
        confluence_data: dict,
        notes: dict,
    ) -> str:
        """Detailed Slack-formatted breakdown used when there is no AI summary"""
        sections = self._activity_sections(
            github_data,
            jira_data,
            confluence_data,
            notes,
            lambda c: f"*{c['repo']}*: {c['message']} (`{c['sha']}`)",
            notes_limit=5,
        )
        if not sections:
            return "No significant activity to report."

        return "\n\n".join(
            f"*{title}*\n" + "\n".join(f"• {line}" for line in lines)
            for title, lines in sections
        )

    def format_standup_blocks(
        self,
        github_data: dict,
        jira_data: dict,
        confluence_data: dict,
        notes: dict,
        ai_summary: Optional[str] = None,
    ) -> list[dict]:
        """Format all data into Slack Block Kit format"""
        date_range, period = self._header_info()

        if ai_summary and ai_summary.strip():
            progress_text = ai_summary
        else:
            progress_text = self._blocks_progress_text(
                github_data, jira_data, confluence_data, notes
            )

        plan_text = "\n".join(f"• {line}" for line in self._plan_lines(notes))

        return [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Daily Standup - {date_range}",
                },
            },
            self._mrkdwn_section(f"*{period}*\n{progress_text}"),
            {"type": "divider"},
            self._mrkdwn_section(f"*Today's Plan*\n{plan_text}"),
            self._mrkdwn_section("*Blockers*\n• None"),
        ]

    def generate_ai_summary(
        self,
        github_data: dict,
        jira_data: dict,
        confluence_data: dict,
        notes: list[str],
    ) -> Optional[str]:
        """Generate an AI summary of the work completed"""
        if not self.config.get("ai_summary", {}).get("enabled", False):
            return None

        provider = self.config["ai_summary"].get("provider", "none")

        # Prepare data for AI
        summary_data = {
            "commits": github_data.get("commits", []),
            "prs_opened": github_data.get("prs_opened", []),
            "prs_merged": github_data.get("prs_merged", []),
            "reviews": github_data.get("reviews", []),
            "jira_completed": jira_data.get("completed", []),
            "jira_updated": jira_data.get("updated", []),
            "jira_in_progress": jira_data.get("in_progress", []),
            "confluence_created": confluence_data.get("created", []),
            "confluence_updated": confluence_data.get("updated", []),
            "personal_notes": notes,
        }

        # Check if there's any meaningful data
        total_items = (
            len(summary_data["commits"])
            + len(summary_data["prs_opened"])
            + len(summary_data["prs_merged"])
            + len(summary_data["reviews"])
            + len(summary_data["jira_completed"])
            + len(summary_data["jira_updated"])
            + len(summary_data["jira_in_progress"])
            + len(summary_data["confluence_created"])
            + len(summary_data["confluence_updated"])
            + len(summary_data["personal_notes"])
        )

        if total_items == 0:
            return "No significant activity found to summarize."

        if provider == "openai" and self.openai_api_key:
            return self._generate_openai_summary(summary_data)
        elif provider == "anthropic" and self.anthropic_api_key:
            return self._generate_anthropic_summary(summary_data)
        else:
            return self._generate_simple_summary(summary_data)

    def _generate_openai_summary(self, data: dict) -> str:
        """Generate summary using OpenAI API"""
        try:
            prompt_style = self.config["ai_summary"].get(
                "prompt_style", "professional"
            )
            model = self.config["ai_summary"].get("model", "gpt-4o-mini")

            prompt = self._build_ai_prompt(data, prompt_style)

            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that creates concise, professional daily standup summaries.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 300,
                "temperature": 0.3,
            }

            headers = {
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json",
            }

            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers=headers,
            )

            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"].strip()
            else:
                print(f"OpenAI API error: {response.status_code}")
                return self._generate_simple_summary(data)

        except Exception as e:
            print(f"Error generating OpenAI summary: {e}")
            return self._generate_simple_summary(data)

    def _generate_anthropic_summary(self, data: dict) -> str:
        """Generate summary using Anthropic Claude API"""
        try:
            prompt_style = self.config["ai_summary"].get(
                "prompt_style", "professional"
            )
            model = self.config["ai_summary"].get(
                "model", "claude-3-haiku-20240307"
            )

            prompt = self._build_ai_prompt(data, prompt_style)

            payload = {
                "model": model,
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            }

            headers = {
                "x-api-key": self.anthropic_api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            }

            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=headers,
            )

            if response.status_code == 200:
                result = response.json()
                return result["content"][0]["text"].strip()
            else:
                print(f"Anthropic API error: {response.status_code}")
                return self._generate_simple_summary(data)

        except Exception as e:
            print(f"Error generating Anthropic summary: {e}")
            return self._generate_simple_summary(data)

    # Per-style (intro, instruction) wrapped around the activity summary
    _PROMPT_STYLES = {
        "casual": (
            "Here's what I got done recently:",
            "Please write a brief, casual daily standup summary (2-3 sentences) highlighting the key accomplishments. Keep it friendly and conversational.",
        ),
        "detailed": (
            "Work Activity Summary:",
            "Please create a detailed daily standup summary that categorizes the work and provides context about impact and progress. Include technical details where relevant.",
        ),
        "professional": (
            "Recent Work Activity:",
            "Please create a concise, professional daily standup summary (2-3 sentences) focusing on key accomplishments and their business impact.",
        ),
    }

    @staticmethod
    def _ai_activity_lines(data: dict) -> list[str]:
        """Plain-text list of the activity to send to the model"""

        def commit(c: dict) -> str:
            return f"{c['message']} ({c['repo']})"

        def pr(p: dict) -> str:
            return f"{p['title']} ({p['repo']})"

        def ticket(t: dict) -> str:
            return f"{t['key']}: {t['summary']}"

        groups = [
            ("GitHub Commits:", data["commits"][:5], commit),
            ("Pull Requests Merged:", data["prs_merged"], pr),
            ("Pull Requests Opened:", data["prs_opened"], pr),
            ("Jira Tickets Completed:", data["jira_completed"], ticket),
            ("Jira Tickets Updated:", data["jira_updated"][:3], ticket),
            ("Other Activities:", data["personal_notes"][:3], str),
        ]

        lines: list[str] = []
        for title, items, format_item in groups:
            if items:
                lines.append(title)
                lines.extend(f"- {format_item(item)}" for item in items)
            # Reviews are summarised as a count, between PRs and Jira
            if title == "Pull Requests Opened:" and data["reviews"]:
                lines.append(
                    f"Code Reviews: {len(data['reviews'])} PRs reviewed"
                )
        return lines

    def _build_ai_prompt(self, data: dict, style: str) -> str:
        """Build the AI prompt based on data and style"""
        intro, instruction = self._PROMPT_STYLES.get(
            style, self._PROMPT_STYLES["professional"]
        )
        activity_summary = "\n".join(self._ai_activity_lines(data))
        return f"{intro}\n\n{activity_summary}\n\n{instruction}"

    def _generate_simple_summary(self, data: dict) -> str:
        """Generate a simple summary without AI"""
        summary_parts = []

        total_commits = len(data["commits"])
        total_prs = len(data["prs_merged"]) + len(data["prs_opened"])
        total_reviews = len(data["reviews"])
        total_tickets = len(data["jira_completed"]) + len(data["jira_updated"])
        total_notes = len(data["personal_notes"])

        if total_commits > 0:
            summary_parts.append(f"{total_commits} commits")
        if total_prs > 0:
            summary_parts.append(f"{total_prs} PRs")
        if total_reviews > 0:
            summary_parts.append(f"{total_reviews} reviews")
        if total_tickets > 0:
            summary_parts.append(f"{total_tickets} Jira tickets")
        if total_notes > 0:
            summary_parts.append(f"{total_notes} other tasks")

        if summary_parts:
            return f"Completed: {', '.join(summary_parts)}."
        else:
            return "No significant activity to report."

    def post_to_slack(
        self, blocks: Optional[list[dict]] = None, message: Optional[str] = None
    ) -> bool:
        """Post message to Slack via webhook using Block Kit or fallback text"""
        if not self.slack_webhook:
            print("Slack webhook URL not configured")
            return False

        # Prefer blocks format over text
        if blocks:
            payload = {
                # "channel": self.config["slack"]["channel"],
                "channel": "@kris.cotten",
                "username": self.config["slack"]["username"],
                "icon_emoji": self.config["slack"]["icon_emoji"],
                "blocks": blocks,
            }
        elif message:
            payload = {
                "channel": self.config["slack"]["channel"],
                "username": self.config["slack"]["username"],
                "icon_emoji": self.config["slack"]["icon_emoji"],
                "text": message,
            }
        else:
            print("No content to post to Slack")
            return False

        try:
            response = requests.post(self.slack_webhook, json=payload)
            return response.status_code == 200
        except Exception as e:
            print(f"Error posting to Slack: {e}")
            return False

    def _collect_github(self, debug: bool) -> dict:
        print("Fetching GitHub activity...")
        github_data = self.get_github_activity()
        if debug:
            print(
                f"GitHub data: {len(github_data.get('commits', []))} commits, {len(github_data.get('prs_merged', []))} merged PRs"
            )
        return github_data

    def _collect_jira(self, debug: bool) -> dict:
        print("Fetching Jira activity...")
        jira_data = self.get_jira_activity()
        if debug:
            if "error" in jira_data:
                print(f"Jira error: {jira_data['error']}")
            else:
                print(
                    f"Jira data: {len(jira_data.get('completed', []))} completed, {len(jira_data.get('updated', []))} updated, {len(jira_data.get('in_progress', []))} in progress"
                )
        return jira_data

    def _collect_notes(self, debug: bool) -> dict[str, list[str]]:
        print("Reading personal notes...")
        notes = self.get_personal_notes()
        if debug:
            print(
                f"Personal notes: {len(notes.get('completed', []))} completed items, {len(notes.get('plan', []))} plan items"
            )
        return notes

    def _collect_confluence(self, debug: bool) -> dict:
        print("Fetching Confluence activity...")
        confluence_data = self.get_confluence_activity()
        if debug:
            if "error" in confluence_data:
                print(f"Confluence error: {confluence_data['error']}")
            else:
                print(
                    f"Confluence data: {len(confluence_data.get('created', []))} created, "
                    f"{len(confluence_data.get('updated', []))} updated"
                )
        return confluence_data

    def _collect_ai_summary(
        self,
        github_data: dict,
        jira_data: dict,
        confluence_data: dict,
        notes: dict[str, list[str]],
        debug: bool,
    ) -> Optional[str]:
        if not self.config.get("ai_summary", {}).get("enabled", False):
            if debug:
                print("AI summary disabled in config")
            return None

        print("Generating AI summary...")
        ai_summary = self.generate_ai_summary(
            github_data,
            jira_data,
            confluence_data,
            notes.get("completed", []),
        )
        if debug:
            print(
                f"AI summary generated: {ai_summary[:100] if ai_summary else 'None'}..."
            )
        return ai_summary

    def _post_standup(self, blocks: list[dict], message: str) -> None:
        """Post to Slack, trying rich blocks first and falling back to text"""
        print("Posting to Slack...")
        if self.post_to_slack(blocks=blocks):
            print("✅ Successfully posted to Slack with rich formatting!")
        elif self.post_to_slack(message=message):
            print("✅ Posted to Slack with basic formatting (blocks failed)")
        else:
            print("❌ Failed to post to Slack")

    def generate_standup(
        self,
        dry_run: bool = False,
        post_to_slack: bool = False,
        debug: bool = False,
    ) -> str:
        """Generate the complete standup message"""
        if dry_run:
            print("🧪 DRY RUN MODE - No data will be posted to Slack")
            print("=" * 50)

        github_data = self._collect_github(debug)
        jira_data = self._collect_jira(debug)
        notes = self._collect_notes(debug)
        confluence_data = self._collect_confluence(debug)
        ai_summary = self._collect_ai_summary(
            github_data, jira_data, confluence_data, notes, debug
        )

        print("Formatting standup message...")
        blocks = self.format_standup_blocks(
            github_data, jira_data, confluence_data, notes, ai_summary
        )
        if debug:
            print("Slack blocks:", blocks)
        message = self.format_standup_message(
            github_data, jira_data, confluence_data, notes, ai_summary
        )

        if post_to_slack and not dry_run:
            self._post_standup(blocks, message)
        elif post_to_slack and dry_run:
            print("🚫 Skipping Slack post due to dry run mode")

        return message


def main():
    parser = argparse.ArgumentParser(
        description="Generate daily standup from multiple sources"
    )
    parser.add_argument(
        "--post", action="store_true", help="Post to Slack automatically"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview mode - fetch data but do not post to Slack",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Show detailed debug information"
    )
    parser.add_argument(
        "--config",
        default="standup_config.json",
        help="Configuration file path",
    )

    args = parser.parse_args()

    # Dry run mode takes precedence over post
    if args.dry_run:
        post_to_slack = False
        dry_run = True
    else:
        post_to_slack = args.post
        dry_run = False

    generator = StandupGenerator(args.config)
    message = generator.generate_standup(
        dry_run=dry_run, post_to_slack=post_to_slack, debug=args.debug
    )

    print("\n" + "=" * 50)
    if dry_run:
        print("DRY RUN - PREVIEW OF STANDUP MESSAGE:")
    else:
        print("GENERATED STANDUP MESSAGE:")
    print("=" * 50)
    print(message)

    if not args.post and not dry_run:
        print("\n💡 Options:")
        print("  --dry-run    Preview with real data (safe for testing)")
        print("  --debug      Show debug information")
        print("  --post       Generate and post to Slack")
    elif dry_run:
        print("\n✅ Dry run complete! Use --post to actually send to Slack")
        if not args.debug:
            print("💡 Use --debug to see detailed API information")


if __name__ == "__main__":
    main()
