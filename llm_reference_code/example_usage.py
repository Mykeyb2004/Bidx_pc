"""
LLM 集成使用示例

演示了各种常见的使用场景和最佳实践
"""

from config import Config
from ai_client import AIClient


def example_1_basic_usage():
    """示例1：基础使用"""
    print("=" * 60)
    print("示例1：基础使用")
    print("=" * 60)
    
    # 加载配置
    config = Config("config.yaml")
    
    # 初始化客户端
    client = AIClient(config)
    
    # 同步调用
    print("\n[同步调用]")
    response = client.chat("你好，请用一句话介绍人工智能", stream=False)
    print(response)
    
    # 流式调用
    print("\n[流式调用]")
    for chunk in client.chat("请列举3个AI应用场景", stream=True):
        print(chunk, end='', flush=True)
    print("\n")


def example_2_without_config_file():
    """示例2：不使用配置文件"""
    print("=" * 60)
    print("示例2：不使用配置文件")
    print("=" * 60)
    
    # 直接传参初始化
    client = AIClient(
        base_url="https://api.openai.com/v1",
        api_key="sk-your-api-key",
        model="gpt-4"
    )
    
    response = client.chat("你好", stream=False)
    print(response)


def example_3_custom_parameters():
    """示例3：自定义参数"""
    print("=" * 60)
    print("示例3：自定义参数")
    print("=" * 60)
    
    config = Config("config.yaml")
    client = AIClient(config)
    
    # 自定义 system message 和参数
    response = client.chat(
        user_message="讲一个笑话",
        system_message="你是一位幽默风趣的喜剧演员",
        temperature=1.2,  # 更高的创造性
        max_tokens=500,
        stream=False
    )
    print(response)


def example_4_multi_turn_conversation():
    """示例4：多轮对话"""
    print("=" * 60)
    print("示例4：多轮对话")
    print("=" * 60)
    
    config = Config("config.yaml")
    client = AIClient(config)
    
    # 构建对话历史
    messages = [
        {"role": "system", "content": "你是一位专业的Python编程助手"},
        {"role": "user", "content": "什么是列表推导式？"},
        {"role": "assistant", "content": "列表推导式是Python中一种简洁的创建列表的方法..."},
        {"role": "user", "content": "请给我一个例子"}
    ]
    
    response = client.chat_with_history(messages, stream=False)
    print(response)


def example_5_stream_with_buffer():
    """示例5：流式输出优化（使用缓冲区）"""
    print("=" * 60)
    print("示例5：流式输出优化")
    print("=" * 60)
    
    config = Config("config.yaml")
    client = AIClient(config)
    
    buffer = []
    for chunk in client.chat("请介绍一下机器学习", stream=True):
        buffer.append(chunk)
        if len(buffer) >= 10:  # 每 10 个 chunk 刷新一次
            print(''.join(buffer), end='', flush=True)
            buffer.clear()
    
    # 输出剩余内容
    if buffer:
        print(''.join(buffer), end='', flush=True)
    print("\n")


def example_6_error_handling():
    """示例6：错误处理"""
    print("=" * 60)
    print("示例6：错误处理")
    print("=" * 60)
    
    config = Config("config.yaml")
    client = AIClient(config)
    
    try:
        response = client.chat("你好", stream=False)
        print(response)
    except Exception as e:
        print(f"❌ API 调用失败: {e}")
        print("可以在这里实现重试逻辑或降级处理")


def example_7_context_from_file():
    """示例7：从文件加载上下文"""
    print("=" * 60)
    print("示例7：从文件加载上下文")
    print("=" * 60)
    
    config = Config("config.yaml")
    client = AIClient(config)
    
    # 假设配置文件中有 context_file 配置项
    try:
        context = config.get_text_from_file_or_config('context')
        
        user_question = "根据上述内容，总结主要观点"
        full_prompt = f"{context}\n\n{user_question}"
        
        response = client.chat(full_prompt, stream=False)
        print(response)
    except Exception as e:
        print(f"无法加载上下文: {e}")


def example_8_different_models():
    """示例8：使用不同的模型"""
    print("=" * 60)
    print("示例8：使用不同的模型")
    print("=" * 60)
    
    # GPT-4
    print("\n[使用 GPT-4]")
    client_gpt4 = AIClient(
        base_url="https://api.openai.com/v1",
        api_key="sk-your-api-key",
        model="gpt-4"
    )
    
    # Gemini
    print("\n[使用 Gemini]")
    client_gemini = AIClient(
        base_url="https://api.ssopen.top/v1",
        api_key="sk-your-api-key",
        model="gemini-2.5-pro"
    )
    
    # 本地模型（Ollama）
    print("\n[使用本地模型]")
    client_local = AIClient(
        base_url="http://localhost:11434/v1",
        api_key="ollama",  # Ollama 不需要真实的 API key
        model="llama2"
    )


def example_9_batch_processing():
    """示例9：批量处理"""
    print("=" * 60)
    print("示例9：批量处理")
    print("=" * 60)
    
    config = Config("config.yaml")
    client = AIClient(config)
    
    questions = [
        "什么是人工智能？",
        "什么是机器学习？",
        "什么是深度学习？"
    ]
    
    results = []
    for i, question in enumerate(questions, 1):
        print(f"\n处理问题 {i}/{len(questions)}: {question}")
        try:
            response = client.chat(question, stream=False)
            results.append({
                "question": question,
                "answer": response,
                "success": True
            })
            print(f"✅ 完成")
        except Exception as e:
            results.append({
                "question": question,
                "error": str(e),
                "success": False
            })
            print(f"❌ 失败: {e}")
    
    # 输出统计
    success_count = sum(1 for r in results if r["success"])
    print(f"\n总计: {len(questions)} 个问题, 成功: {success_count}, 失败: {len(questions) - success_count}")


def main():
    """运行所有示例"""
    examples = [
        example_1_basic_usage,
        # example_2_without_config_file,
        # example_3_custom_parameters,
        # example_4_multi_turn_conversation,
        # example_5_stream_with_buffer,
        # example_6_error_handling,
        # example_7_context_from_file,
        # example_8_different_models,
        # example_9_batch_processing,
    ]
    
    print("\n" + "=" * 60)
    print("LLM 集成使用示例")
    print("=" * 60)
    print("\n提示：请先配置 config.yaml 文件，然后取消注释想要运行的示例\n")
    
    for example in examples:
        try:
            example()
            print()
        except Exception as e:
            print(f"\n❌ 示例运行失败: {e}\n")


if __name__ == "__main__":
    main()
