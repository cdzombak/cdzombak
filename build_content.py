from python_graphql_client import GraphqlClient
import feedparser
import httpx
import json
import pathlib
import re
import os

root = pathlib.Path(__file__).parent.resolve()
client = GraphqlClient(endpoint="https://api.github.com/graphql")

TOKEN = os.environ.get("CDZOMBAK_TOKEN", "")

SKIP_REPOS = {

}


def replace_chunk(content, marker, chunk, inline=False):
    r = re.compile(
        r"<!\-\- {} starts \-\->.*<!\-\- {} ends \-\->".format(marker, marker),
        re.DOTALL,
    )
    if not inline:
        chunk = "\n{}\n".format(chunk)
    chunk = "<!-- {} starts -->{}<!-- {} ends -->".format(marker, chunk, marker)
    return r.sub(chunk, content)


GRAPHQL_SEARCH_QUERY = """
query {
  search(first: 100, type:REPOSITORY, query:"is:public owner:cdzombak sort:updated", after: AFTER) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      __typename
      ... on Repository {
        name
        description
        url
        releases(orderBy: {field: CREATED_AT, direction: DESC}, first: 1) {
          totalCount
          nodes {
            name
            publishedAt
            url
          }
        }
      }
    }
  }
}
"""


def make_query(after_cursor=None, include_organization=False):
    return GRAPHQL_SEARCH_QUERY.replace(
        "AFTER", '"{}"'.format(after_cursor) if after_cursor else "null"
    )


def fetch_releases(oauth_token):
    repos = []
    releases = []
    # Skip these repos:
    repo_names = set(SKIP_REPOS)
    has_next_page = True
    after_cursor = None

    first = True

    while has_next_page:
        data = client.execute(
            query=make_query(after_cursor, include_organization=first),
            headers={"Authorization": "Bearer {}".format(oauth_token)},
        )
        first = False
        print()
        print(json.dumps(data, indent=4))
        print()
        repo_nodes = data["data"]["search"]["nodes"]
        for repo in repo_nodes:
            if repo["releases"]["totalCount"] and repo["releases"]["nodes"][0]["publishedAt"] and repo["name"] not in repo_names:
                repos.append(repo)
                repo_names.add(repo["name"])
                releases.append(
                    {
                        "repo": repo["name"],
                        "repo_url": repo["url"],
                        "description": repo["description"],
                        "release": repo["releases"]["nodes"][0]["name"]
                        .replace(repo["name"], "")
                        .strip(),
                        "published_at": repo["releases"]["nodes"][0]["publishedAt"],
                        "published_day": repo["releases"]["nodes"][0][
                            "publishedAt"
                        ].split("T")[0],
                        "url": repo["releases"]["nodes"][0]["url"],
                        "total_releases": repo["releases"]["totalCount"],
                    }
                )
        after_cursor = data["data"]["search"]["pageInfo"]["endCursor"]
        has_next_page = after_cursor
    return releases


# def fetch_tils():
#     sql = """
#         select path, replace(title, '_', '\_') as title, url, topic, slug, created_utc
#         from til order by created_utc desc limit 6
#     """.strip()
#     return httpx.get(
#         "https://til.simonwillison.net/tils.json",
#         params={
#             "sql": sql,
#             "_shape": "array",
#         },
#     ).json()


def fetch_blog_entries():
    entries = feedparser.parse("https://www.dzombak.com/blog/rss/")["entries"]
    return [
        {
            "title": entry["title"],
            "url": entry["link"].split("#")[0],
            "published": entry["published"].split(" ")[1] + " " + entry["published"].split(" ")[2] + " " + entry["published"].split(" ")[3],
        }
        for entry in entries
    ]


if __name__ == "__main__":
    releases = fetch_releases(TOKEN)
    releases.sort(key=lambda r: r["published_at"], reverse=True)

    readme = root / "README.md"
    readme_contents = readme.open().read()
    releases_md = "\n\n".join(
        [
            "[{repo} {release}]({url}) *({published_day})*".format(**release)
            for release in releases[:8]
        ]
    )
    rewritten_readme = replace_chunk(readme_contents, "recent_releases", releases_md)
    entries = fetch_blog_entries()[:6]
    entries_md = "\n\n".join(
        ["[{title}]({url}) *({published})*".format(**entry) for entry in entries]
    )
    rewritten_readme = replace_chunk(rewritten_readme, "blog", entries_md)
    readme.open("w").write(rewritten_readme)

    # Write out full project-releases.md file
    project_releases = root / "RELEASES.md"
    project_releases_md = "\n".join(
        [
            (
                "* **[{repo}]({repo_url})**: [{release}]({url}) *({published_day}; {total_releases_md})* \n"
                "<br />{description}"
            ).format(
                total_releases_md="[{} releases total]({}/releases) ".format(
                    release["total_releases"], release["repo_url"]
                )
                if release["total_releases"] > 1
                else "",
                **release
            )
            for release in releases
        ]
    )
    project_releases_content = project_releases.open().read()
    project_releases_content = replace_chunk(
        project_releases_content, "recent_releases", project_releases_md
    )
    project_releases_content = replace_chunk(
        project_releases_content, "project_count", str(len(releases)), inline=True
    )
    project_releases_content = replace_chunk(
        project_releases_content,
        "releases_count",
        str(sum(r["total_releases"] for r in releases)),
        inline=True,
    )
    project_releases.open("w").write(project_releases_content)
