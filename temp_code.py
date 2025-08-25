# 请从下面的 CorrectedMethods 类中复制三个方法，
# 并用它们替换您在 kv_tree_app.py 中的 add_folder 方法。

class CorrectedMethods:
    def add_folder(self):
        """添加一个文件夹，并启动后台预扫描。"""
        folder_path = filedialog.askdirectory(title="选择要扫描的文件夹")
        if not folder_path:
            return

        folder_path = os.path.normpath(folder_path)
        if folder_path in self.source_files:
            messagebox.showinfo("提示", "该文件夹已在源列表中。")
            return

        self.set_status(f"正在预扫描文件夹: {folder_path}...")
        self.progress_bar.start()
        
        # 使用后台线程进行扫描，避免UI冻结
        thread = threading.Thread(target=self.scan_folder_worker, args=(folder_path,), daemon=True)
        thread.start()

    def scan_folder_worker(self, folder_path):
        """在后台线程中扫描文件夹以查找.md文件。"""
        file_count = 0
        total_size = 0
        scanned_files = {} # {path: mtime}

        try:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    if file.endswith('.md'):
                        file_path = os.path.normpath(os.path.join(root, file))
                        file_count += 1
                        try:
                            file_size = os.path.getsize(file_path)
                            total_size += file_size
                            scanned_files[file_path] = os.path.getmtime(file_path)
                        except OSError:
                            continue # 忽略无法访问的文件
        except Exception as e:
            # 在主线程中显示错误
            self.after(0, lambda: messagebox.showerror("扫描错误", f"扫描文件夹时发生错误: {e}"))
            return
        finally:
            # 确保在主线程中停止进度条并更新UI
            self.after(0, self.progress_bar.stop)
            self.after(0, self.show_scan_results, folder_path, file_count, total_size, scanned_files)

    def show_scan_results(self, folder_path, file_count, total_size, scanned_files):
        """在主线程中显示扫描结果并请求用户确认。"""
        if file_count == 0:
            messagebox.showinfo("扫描完成", f"在 '{os.path.basename(folder_path)}' 中没有找到.md文件。")
            self.set_status("就绪")
            return

        size_mb = total_size / (1024 * 1024)
        msg = f"""
文件夹 '{os.path.basename(folder_path)}' 扫描完成。

发现 {file_count} 个 .md 文件
总大小: {size_mb:.2f} MB

是否要将其添加到源列表？
        """.strip()

        if messagebox.askyesno("确认添加", msg):
            self.source_files[folder_path] = {
                "enabled": True, 
                "type": "folder",
                "files": scanned_files, # 存储扫描到的文件及其mtime
                "mtime": os.path.getmtime(folder_path) # 存储文件夹本身的mtime
            }
            self.update_source_list()
            self.set_status(f"已添加文件夹: {folder_path}")
        else:
            self.set_status("操作已取消。")
