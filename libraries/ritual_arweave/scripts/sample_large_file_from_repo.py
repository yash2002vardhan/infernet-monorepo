from ritual_arweave.repo_manager import RepoManager

if __name__ == "__main__":
    repo = "your-arweave-address/gemma-1.1-2b-it_Q4_KM"
    RepoManager(show_progress_bar=True).download_file_in_repo(
        repo, file_name="gemma-1.1-2b-it-Q4_K_M.gguf", base_path="./llama"
    )
