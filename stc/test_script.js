// 无人机重量计算器 - 自动化测试脚本
// 在浏览器控制台运行此脚本进行快速测试

console.log('=== 无人机重量计算器测试开始 ===\n');

// 测试辅助函数
function assert(condition, message) {
    if (condition) {
        console.log('✅', message);
        return true;
    } else {
        console.error('❌', message);
        return false;
    }
}

function getTotalWeight() {
    const enabledItems = items.filter(item => item.enabled);
    return enabledItems.reduce((sum, item) => sum + (item.qty * item.weightPerUnit), 0);
}

function getTotalWeightKg() {
    return getTotalWeight() / 1000;
}

function getWeightPerMotor() {
    if (project.rotorCount <= 0) return 0;
    return getTotalWeightKg() / project.rotorCount;
}

function getTWRatio() {
    if (!project.motorThrust || project.rotorCount <= 0) return null;
    const totalThrust = project.motorThrust * project.rotorCount;
    return totalThrust / getTotalWeight();
}

// 测试 1: 基础计算
console.log('--- 测试 1: 基础计算 ---');
const calculatedTotal = getTotalWeight();
const displayedTotal = parseFloat(document.getElementById('totalWeightG').textContent.replace(' g', ''));
assert(Math.abs(calculatedTotal - displayedTotal) < 0.01, 
    `总重量计算: 计算值=${calculatedTotal.toFixed(2)}g, 显示值=${displayedTotal.toFixed(2)}g`);

const calculatedKg = getTotalWeightKg();
const displayedKg = parseFloat(document.getElementById('totalWeightKg').textContent.replace(' kg', ''));
assert(Math.abs(calculatedKg - displayedKg) < 0.001, 
    `总重量(kg): 计算值=${calculatedKg.toFixed(3)}kg, 显示值=${displayedKg.toFixed(3)}kg`);

const calculatedPerMotor = getWeightPerMotor();
const displayedPerMotor = parseFloat(document.getElementById('weightPerMotor').textContent.replace(' kg', ''));
assert(Math.abs(calculatedPerMotor - displayedPerMotor) < 0.001, 
    `每电机负载: 计算值=${calculatedPerMotor.toFixed(3)}kg, 显示值=${displayedPerMotor.toFixed(3)}kg`);

// 测试 2: 启用/禁用过滤
console.log('\n--- 测试 2: 启用/禁用过滤 ---');
const enabledCount = items.filter(item => item.enabled).length;
const disabledCount = items.filter(item => !item.enabled).length;
console.log(`已启用项目: ${enabledCount}, 已禁用项目: ${disabledCount}`);

// 手动计算已启用项目的总重量
let manualTotal = 0;
items.forEach(item => {
    if (item.enabled) {
        manualTotal += item.qty * item.weightPerUnit;
    }
});
assert(Math.abs(manualTotal - calculatedTotal) < 0.01, 
    `启用/禁用过滤: 手动计算=${manualTotal.toFixed(2)}g, 函数计算=${calculatedTotal.toFixed(2)}g`);

// 测试 3: 分类统计
console.log('\n--- 测试 3: 分类统计 ---');
const categoryBreakdown = {};
items.forEach(item => {
    if (item.enabled) {
        if (!categoryBreakdown[item.category]) {
            categoryBreakdown[item.category] = 0;
        }
        categoryBreakdown[item.category] += item.qty * item.weightPerUnit;
    }
});

let categorySum = 0;
Object.values(categoryBreakdown).forEach(weight => {
    categorySum += weight;
});
assert(Math.abs(categorySum - calculatedTotal) < 0.01, 
    `分类统计总和: ${categorySum.toFixed(2)}g, 总重量: ${calculatedTotal.toFixed(2)}g`);

// 测试 4: 推重比计算
console.log('\n--- 测试 4: 推重比计算 ---');
if (project.motorThrust && project.rotorCount > 0) {
    const calculatedTW = getTWRatio();
    const twCard = document.getElementById('twCard');
    assert(twCard.style.display !== 'none', '推重比卡片应该显示');
    
    if (twCard.style.display !== 'none') {
        const displayedTW = parseFloat(document.getElementById('twRatio').textContent);
        assert(Math.abs(calculatedTW - displayedTW) < 0.01, 
            `推重比: 计算值=${calculatedTW.toFixed(2)}, 显示值=${displayedTW.toFixed(2)}`);
        
        const totalThrust = project.motorThrust * project.rotorCount;
        console.log(`  总推力: ${totalThrust}g (${project.motorThrust}g × ${project.rotorCount})`);
        console.log(`  总重量: ${calculatedTotal.toFixed(2)}g`);
        console.log(`  推重比: ${calculatedTW.toFixed(2)}`);
    }
} else {
    console.log('⚠️  未设置电机推力，跳过推重比测试');
}

// 测试 5: 电机数量同步
console.log('\n--- 测试 5: 电机数量UI同步 ---');
const rotorSelect = document.getElementById('rotorCount');
const rotorSelectValue = rotorSelect.value === 'custom' ? 
    parseInt(document.getElementById('customRotorCount').value) : 
    parseInt(rotorSelect.value);
assert(rotorSelectValue === project.rotorCount, 
    `电机数量同步: UI显示=${rotorSelectValue}, 内部值=${project.rotorCount}`);

// 测试 6: 数据完整性
console.log('\n--- 测试 6: 数据完整性 ---');
assert(project.name !== undefined, '项目名称存在');
assert(project.rotorCount > 0, `电机数量有效: ${project.rotorCount}`);
assert(Array.isArray(items), 'items 是数组');
assert(typeof scenarios === 'object', 'scenarios 是对象');

// 测试 7: 项目数据完整性
console.log('\n--- 测试 7: 项目数据完整性 ---');
let allItemsValid = true;
items.forEach((item, index) => {
    if (!item.name || item.qty <= 0 || item.weightPerUnit < 0 || !item.category) {
        console.error(`❌ 项目 ${index} 数据不完整:`, item);
        allItemsValid = false;
    }
});
assert(allItemsValid, '所有项目数据完整');

// 测试 8: 目标比较（如果设置了）
console.log('\n--- 测试 8: 目标比较 ---');
const targetCard = document.getElementById('targetCard');
if (project.targetAUW || project.targetTW) {
    assert(targetCard.style.display !== 'none', '目标比较卡片应该显示');
    if (project.targetAUW) {
        const diff = calculatedTotal - project.targetAUW;
        console.log(`  目标AUW: ${project.targetAUW}g`);
        console.log(`  当前AUW: ${calculatedTotal.toFixed(2)}g`);
        console.log(`  差值: ${diff > 0 ? '+' : ''}${diff.toFixed(2)}g`);
    }
    if (project.targetTW && project.motorThrust) {
        const currentTW = getTWRatio();
        const diff = currentTW - project.targetTW;
        console.log(`  目标T/W: ${project.targetTW}`);
        console.log(`  当前T/W: ${currentTW.toFixed(2)}`);
        console.log(`  差值: ${diff > 0 ? '+' : ''}${diff.toFixed(2)}`);
    }
} else {
    console.log('⚠️  未设置目标，跳过目标比较测试');
}

// 测试 9: 场景数据
console.log('\n--- 测试 9: 场景数据 ---');
const scenarioCount = Object.keys(scenarios).length;
console.log(`场景数量: ${scenarioCount}`);
Object.keys(scenarios).forEach(name => {
    const scenario = scenarios[name];
    assert(Array.isArray(scenario.items), `场景 "${name}" 有 items 数组`);
    if (scenario.items) {
        console.log(`  场景 "${name}": ${scenario.items.length} 个项目`);
    }
});

// 测试 10: 导出数据准备
console.log('\n--- 测试 10: 导出数据准备 ---');
const exportData = {
    project,
    items,
    scenarios
};
assert(exportData.project !== undefined, '导出数据包含 project');
assert(exportData.items !== undefined, '导出数据包含 items');
assert(exportData.scenarios !== undefined, '导出数据包含 scenarios');

console.log('\n=== 测试完成 ===');
console.log('\n提示: 如果所有测试通过，可以继续手动测试 UI 交互和导出功能。');

