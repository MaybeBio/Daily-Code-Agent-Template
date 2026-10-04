我提供一些我想研究的领域内的关键词，也就是该topic关键词，
然后本自动化工具模板能够周期性自动搜索（比如说每天或者每周）该领域该topic的仓库，

1. 首先需要能够从这些query中搜索到这些仓库或代码，可以参考/data2/Daily-Code-Agent-Template/Daily-GitHub-AI4Bio 中的/data2/Daily-Code-Agent-Template/Daily-GitHub-AI4Bio/discovery discovery文件夹，拿到特定topic的每周数据
2. 其次，对于每次获取的列表数据，我们可以返回1个table，可以是在issue中的table，或者是存储在本地的csv表格，可以参考/data2/Daily-Code-Agent-Template/Daily-GitHub-AI4Bio/discovery 中的csv表格，或者是 /data2/Daily-Paper-Agent-Template 存成1个本地csv+issue推送，对，issue推送是必要的，需要在workflow中指定
3. 然后，对于推送得到的仓库，我们不能每次自己去搜索readme再查看这个仓库，再人工筛选，我们得建立1个高效的筛选机制。比如说我们可以参考 /data2/Daily-Paper-Agent-Template，也就是 /data2/Daily-Paper-Agent-Template/prompts.yaml，我们可以类似搞一个打分，比如说给仓库的readme，然后结合我们的topic，看看这个仓库或代码能否给我们提供灵感，怎么使用等；然后在issue中同样推送：仓库名字、url、最后一个commit更新时间、打分、一句话总结，就是类似 /data2/Daily-Paper-Agent-Template/
4. 那么对于这些仓库我们怎么处理？首先是每个周期搜索、推送到issue中之后，我们可以把每个仓库得分高的进行1次degit，也就是浅拷贝克隆下来。除了浅克隆下来保存一份code文件之外，我们还需要存一些公开的wiki文档，比如说deepwiki、zread、google code wiki文档。也就是说，对于每个周期搜索拿到的仓库列表，我们对每一个仓库新建1个文件夹，然后这个文件夹内存 code/（degit存该仓库的浅克隆）、deepwiki/、zread/、google_code_wiki等。
5. 同样推送除了issue，我们可以搞一个静态pages网站推送，可以参考 /data2/Daily-Paper-Agent-Template，每周一次推送，然后每个仓库搞一个 code card，也是模仿paper，深度解析一下
6. 就是目前有4个问题：
   1. 评分如何使用，高分的才克隆，高分的才进行agent解析吗？那低分的也没有必要在pages中？ 
   2. 另外一个问题就是每次更新拿到同一个仓库怎么办？就是同一个仓库可能会持续更新，比如说这一周拿到了，然后下一周也拿到，那么我们就需要进行更新：首先仓库是能够重新degit覆盖的，但是wiki内容不好更新，wiki内容需要人工自己重新提交重新下载，这个做不到；
   3. 这个自动化工具模板的设计，怎么把上面这些流程整合起来，形成一个完整的自动化流程。也就是从搜索到筛选到推送到克隆到wiki文档整理到静态pages网站推送。
      1. 首先github搜索，可以使用gh搜索，也可以参考 /data2/Daily-Code-Agent-Template/Daily-GitHub-AI4Bio的/data2/Daily-Code-Agent-Template/Daily-GitHub-AI4Bio/discovery/queries/search_idr_repos.yaml，使用我自研的工具ghresearcher中的search功能，参考/data2/Daily-Code-Agent-Template/GhResearcher。至于仓库克隆，使用degit浅克隆；然后是仓库wiki内容复制拷贝，可以使用我自研的另外一个工具repowiki-cli，/data2/Daily-Code-Agent-Template/Repowiki-cli。至于agent部分，也就是issue推送+pages部署，可以参考/data2/Daily-Paper-Agent-Template
   4. 这个自动化工具模板的实现，怎么实现每个步骤的功能，比如说搜索、筛选、推送、克隆、整理wiki文档、生成静态pages网站等。
7. 可以考虑加入huggingface部分，也就是hf cli