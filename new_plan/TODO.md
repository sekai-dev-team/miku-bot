- [ ] 处理不同格式的消息
  - [ ] 图片
  - [ ] emoji
  - [ ] 语音

- [ ] 聊天记录是否还需要？

graph TD
    User[用户输入] --> |正则捕获| Handler[Chat Handler]
    Handler --> |Query| MemSearch[🔍 Memory Search]
    MemSearch --> |返回相关记忆| Context[📝 Prompt 构建]
    Context --> |人设+记忆+历史| AI[🧠 DeepSeek LLM]
    AI --> |生成回复| Reply[🗣️ 发送回复]
    Reply --> User
    
    Reply -.-> |异步任务| MemAdd[📥 Memory Add]
    MemAdd --> |提取事实| MemDB[(📚 ChromaDB)]