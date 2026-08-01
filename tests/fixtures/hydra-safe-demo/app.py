"""Tiny typed application for the deterministic Hydra worker."""


def greet(name: str) -> str:
    """Return a stable greeting."""
    return f"Hello, {name}!"


# HYDRA_AGENT_INSERTION_POINT


if __name__ == "__main__":
    print(greet("Hydra"))
    if "mission_summary" in globals():
        print(mission_summary())
